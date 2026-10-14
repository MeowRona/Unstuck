from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from collections import deque
from contextlib import contextmanager
from threading import RLock, local
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Place


HACKATHON_BASE_URL = "https://hackathon.api.qloo.com"
# Official @qloo/qloo-harness 0.1.26 qloo_rank accepts at most 10 options.
# Keep the live adapter inside that canonical workflow boundary so one Unstuck
# ranking round stays comparable and quota-bounded.
QLOO_MAX_RANK_OPTIONS = 10


@dataclass(frozen=True)
class TasteResult:
    place_id: str
    affinity: float | None
    rank: int | None
    evidence: tuple[str, ...]
    source: str


class TasteResults(list[TasteResult]):
    """List-compatible ranking result with a small, redacted evidence trace."""

    def __init__(self, values=(), *, trace: dict | None = None):
        super().__init__(values)
        self.trace = trace or {}


class FixtureTasteProvider:
    mode = "fixture"

    def __init__(self, mapping_path: Path):
        payload = json.loads(mapping_path.read_text(encoding="utf-8"))
        self.reference_tags: dict[str, dict[str, float]] = payload.get("reference_tags", {})

    def rank(self, places: list[Place], taste_refs: Iterable[str]) -> TasteResults:
        return self.rank_with_context(places, taste_refs, failed_place=None)

    def rank_with_context(
        self,
        places: list[Place],
        taste_refs: Iterable[str],
        *,
        failed_place: str | None,
    ) -> TasteResults:
        refs = [x.strip() for x in taste_refs if x.strip()]
        scored: list[tuple[float, Place, tuple[str, ...]]] = []
        matched_refs: set[str] = set()
        for place in places:
            score = 0.0
            evidence: list[str] = []
            for ref in refs:
                weights = self.reference_tags.get(ref.casefold(), {})
                matched = [tag for tag in place.taste_tags if tag in weights]
                if matched:
                    score += sum(float(weights[tag]) for tag in matched)
                    evidence.append(ref)
                    matched_refs.add(ref)
            if not refs:
                score = 0.0
            scored.append((score, place, tuple(dict.fromkeys(evidence))))
        scored.sort(key=lambda item: (-item[0], item[1].name.casefold()))
        if not scored:
            return TasteResults(
                trace={
                    "status": "fixture_preview",
                    "input_references": refs,
                    "fixture_matches": sorted(matched_refs),
                    "failed_place_anchor": failed_place or None,
                    "anchor_used": False,
                    "discovery_used": False,
                }
            )
        max_score = max((x[0] for x in scored), default=0.0)
        results: list[TasteResult] = []
        for index, (score, place, evidence) in enumerate(scored, start=1):
            affinity = None if not refs else (score / max_score if max_score > 0 else 0.0)
            results.append(
                TasteResult(
                    place_id=place.id,
                    affinity=round(affinity, 4) if affinity is not None else None,
                    rank=index,
                    evidence=evidence,
                    source="fixture",
                )
            )
        return TasteResults(
            results,
            trace={
                "status": "fixture_preview",
                "input_references": refs,
                "fixture_matches": sorted(matched_refs),
                "failed_place_anchor": failed_place or None,
                "anchor_used": False,
                "discovery_used": False,
            },
        )


class NoTasteProvider:
    """Feasibility-only baseline for controlled product comparisons."""

    mode = "baseline"

    def rank(self, places: list[Place], taste_refs: Iterable[str]) -> TasteResults:
        return self.rank_with_context(places, taste_refs, failed_place=None)

    def rank_with_context(
        self,
        places: list[Place],
        taste_refs: Iterable[str],
        *,
        failed_place: str | None,
    ) -> TasteResults:
        refs = [x.strip() for x in taste_refs if x.strip()]
        return TasteResults(
            [TasteResult(place.id, None, None, (), "baseline") for place in places],
            trace={
                "status": "baseline",
                "input_references": refs,
                "failed_place_anchor": failed_place or None,
                "anchor_used": False,
                "discovery_used": False,
            },
        )


class QlooTransport:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = HACKATHON_BASE_URL,
        *,
        max_network_calls: int = 30,
        cache_ttl_seconds: int = 300,
        window_seconds: int = 60,
    ):
        self.api_key = (api_key if api_key is not None else os.environ.get("QLOO_API_KEY", "")).strip()
        self.base_url = base_url.rstrip("/")
        if not self.api_key:
            raise RuntimeError("BLOCKED_NO_API_KEY")
        if max_network_calls < 1:
            raise ValueError("max_network_calls must be at least 1")
        self.max_network_calls = max_network_calls  # rolling window, not process lifetime
        self.window_seconds = max(1, int(window_seconds))
        self.network_calls = 0  # cumulative diagnostics, never a lifetime blocker
        self._recent_calls = deque()
        self._lock = RLock()
        self._request_local = local()
        self.cache_ttl_seconds = max(0, cache_ttl_seconds)
        # Deliberately process-memory only: no Qloo output is persisted to disk.
        # This avoids building a local Qloo database and only deduplicates short-lived calls.
        self._cache: dict[str, tuple[float, dict]] = {}

    @staticmethod
    def _cache_key(path: str, params: dict[str, str | int | float] | None) -> str:
        return json.dumps([path, sorted((params or {}).items())], separators=(",", ":"), ensure_ascii=False)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    @contextmanager
    def request_scope(self, max_calls: int = 18):
        """Limit each planning job separately from the renewable service-wide window."""
        previous = getattr(self._request_local, "remaining", None)
        self._request_local.remaining = min(max(1, max_calls), previous) if previous is not None else max(1, max_calls)
        try:
            yield
        finally:
            if previous is None:
                del self._request_local.remaining
            else:
                self._request_local.remaining = previous

    def _reserve_attempt(self) -> None:
        # Each HTTP attempt, including retries, consumes a token atomically.
        with self._lock:
            now = time.monotonic()
            while self._recent_calls and self._recent_calls[0] <= now - self.window_seconds:
                self._recent_calls.popleft()
            remaining = getattr(self._request_local, "remaining", None)
            if remaining is not None and remaining <= 0:
                raise RuntimeError("QLOO_JOB_BUDGET_EXHAUSTED")
            if len(self._recent_calls) >= self.max_network_calls:
                raise RuntimeError("QLOO_RATE_WINDOW_EXHAUSTED")
            self._recent_calls.append(now)
            self.network_calls += 1
            if remaining is not None:
                self._request_local.remaining = remaining - 1

    def get_json(self, path: str, params: dict[str, str | int | float] | None = None) -> dict:
        if not path.startswith("/"):
            raise ValueError("path must start with /")
        cache_key = self._cache_key(path, params)
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] <= self.cache_ttl_seconds:
                return cached[1]
        query = urlencode(params or {})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        request = Request(url, headers={"X-Api-Key": self.api_key, "Accept": "application/json"})
        last_error: Exception | None = None
        for attempt in range(3):
            self._reserve_attempt()
            try:
                with urlopen(request, timeout=12) as response:
                    raw = response.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise RuntimeError("Qloo response exceeded safety limit")
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise RuntimeError("Unexpected Qloo response")
                if self.cache_ttl_seconds:
                    with self._lock:
                        if len(self._cache) >= 128:
                            oldest = min(self._cache, key=lambda key: self._cache[key][0])
                            self._cache.pop(oldest, None)
                        self._cache[cache_key] = (time.monotonic(), payload)
                return payload
            except HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    raise RuntimeError(f"QLOO_HTTP_{exc.code}") from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = min(2.0, max(0.0, float(retry_after))) if retry_after else 0.3 * (attempt + 1)
                except ValueError:
                    delay = 0.3 * (attempt + 1)
                time.sleep(delay)
            except URLError as exc:
                last_error = exc
                if attempt == 2:
                    raise RuntimeError("QLOO_UNREACHABLE") from exc
                time.sleep(0.25 * (attempt + 1))
        raise RuntimeError("QLOO_REQUEST_FAILED") from last_error


def _entity_rows(payload: dict) -> list[dict]:
    results = payload.get("results")
    if isinstance(results, dict) and isinstance(results.get("entities"), list):
        return [x for x in results["entities"] if isinstance(x, dict)]
    if isinstance(results, list):
        return [x for x in results if isinstance(x, dict)]
    return []


def _entity_id(row: dict) -> str:
    for key in ("entity_id", "id"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _name(row: dict) -> str:
    value = row.get("name")
    return value.strip() if isinstance(value, str) else ""


def _types(row: dict) -> tuple[str, ...]:
    raw = row.get("types", row.get("type", ()))
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list):
        return tuple(x for x in raw if isinstance(x, str))
    return ()


def _affinity(row: dict) -> float | None:
    query = row.get("query")
    if isinstance(query, dict) and isinstance(query.get("affinity"), (int, float)):
        return float(query["affinity"])
    value = row.get("affinity")
    return float(value) if isinstance(value, (int, float)) else None


def _comparable_name(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join("".join(ch if ch.isalnum() else " " for ch in without_marks).split())


def _explainability_evidence(row: dict, interests: list[tuple[str, str]]) -> tuple[str, ...]:
    query = row.get("query")
    if not isinstance(query, dict) or "explainability" not in query:
        return ()
    strings: set[str] = set()

    def collect(value) -> None:
        if isinstance(value, str):
            strings.add(value)
        elif isinstance(value, dict):
            for key, child in value.items():
                if isinstance(key, str):
                    strings.add(key)
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(query.get("explainability"))
    return tuple(name for entity_id, name in interests if entity_id in strings)


class RealQlooProvider:
    """Small live adapter. It never falls back silently when live mode fails."""

    mode = "live"

    def __init__(self, transport: QlooTransport | None = None):
        self.transport = transport or QlooTransport()
        # Public, unauthenticated entity search should not consume the entire
        # hackathon quota. These process-local counters are deliberately separate
        # from the actual planning/Insights quota and store no IPs or user queries.
        self._picker_lock = RLock()
        self._picker_attempts = deque()

    def _reserve_picker_lookup(self) -> None:
        with self._picker_lock:
            now = time.monotonic()
            while self._picker_attempts and self._picker_attempts[0] <= now - 3600:
                self._picker_attempts.popleft()
            recent_minute = sum(value > now - 60 for value in self._picker_attempts)
            if recent_minute >= 12 or len(self._picker_attempts) >= 72:
                raise RuntimeError("QLOO_PICKER_RATE_LIMITED")
            self._picker_attempts.append(now)

    def _resolve(self, name: str, *, entity_type: str | None = None) -> tuple[str, str]:
        # A short Qloo /search page can miss an exact venue name behind
        # similarly named businesses. Ask for ten rather than five *in the
        # same single request* for places. Taste entities keep their smaller
        # five-result search. Do not retry aliases or spend extra network calls.
        params: dict[str, str | int] = {
            "query": name,
            "take": 10 if entity_type == "urn:entity:place" else 5,
        }
        if entity_type:
            params["types"] = entity_type
        try:
            payload = self.transport.get_json("/search", params)
        except RuntimeError as exc:
            # Official Qloo /search documents HTTP 404 as "No results".
            # A missing seed or venue is not a connection outage, and must
            # not cause the entire operational plan to fail.
            if str(exc) == "QLOO_HTTP_404":
                raise ValueError(f"Qloo entity not found: {name}") from exc
            raise
        rows = _entity_rows(payload)
        comparable = _comparable_name(name)
        exact = [
            (row, _entity_id(row), _name(row))
            for row in rows
            if _comparable_name(_name(row)) == comparable
            and (not entity_type or entity_type in _types(row))
        ]
        # An API search can return multiple copies of the same entity. Distinct
        # result rows are not necessarily distinct matches.
        exact_by_id = {entity_id: resolved_name for _row, entity_id, resolved_name in exact if entity_id}
        if len(exact_by_id) == 1:
            return next(iter(exact_by_id.items()))
        if not rows:
            raise ValueError(f"Qloo could not resolve interest: {name}")
        options = ", ".join(_name(row) for row in rows[:3] if _name(row))
        raise ValueError(f"Ambiguous Qloo interest '{name}'. Matches: {options}")

    def suggest_taste_entities(self, name: str, kind: str = "artist") -> list[dict[str, str]]:
        """Explicit user-triggered Qloo search: one request, no eager lookups."""
        kinds = {
            "artist": "urn:entity:artist",
            "movie": "urn:entity:movie",
            "book": "urn:entity:book",
            "tv_show": "urn:entity:tv_show",
        }
        if kind not in kinds:
            raise ValueError("taste type must be artist, movie, book or tv_show")
        if not isinstance(name, str) or not 2 <= len(name.strip()) <= 70:
            raise ValueError("taste search must contain 2–70 characters")
        if any(ord(char) < 32 for char in name):
            raise ValueError("taste search contains invalid characters")
        self._reserve_picker_lookup()
        with self.transport.request_scope(max_calls=1):
            try:
                payload = self.transport.get_json(
                    "/search", {"query": name.strip(), "types": kinds[kind], "take": 6}
                )
            except RuntimeError as exc:
                if str(exc) == "QLOO_HTTP_404":
                    return []
                raise
        options: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in _entity_rows(payload):
            entity_id, display_name = _entity_id(row), _name(row)
            if (not entity_id or not display_name or kinds[kind] not in _types(row)
                    or not re.fullmatch(r"[A-Za-z0-9_:/.-]{3,160}", entity_id)
                    or entity_id in seen):
                continue
            seen.add(entity_id)
            options.append({"id": entity_id, "name": display_name[:80], "kind": kind})
        return options[:6]

    def resolve_interest(self, name: str) -> tuple[str, str]:
        # A choice from the explicit Qloo picker avoids a second ambiguous /search
        # request; Insights still determines whether this entity actually ranks.
        # A submitted id is not evidence of a successful insight.
        if name.startswith("qloo-id:"):
            payload = name[len("qloo-id:"):].split("|")
            if len(payload) != 3:
                raise ValueError("Invalid selected Qloo entity")
            entity_id, kind, title = payload
            if (not re.fullmatch(r"[A-Za-z0-9_:/.-]{3,160}", entity_id)
                    or kind not in {"artist", "movie", "book", "tv_show"}
                    or not 1 <= len(title) <= 80 or any(ch in "|," or ord(ch) < 32 for ch in title)):
                raise ValueError("Invalid selected Qloo entity")
            return entity_id, title
        # Explicit domain hints make ambiguous cultural references resolvable
        # without secretly guessing which "Amelie" or "Radiohead" was meant.
        hints = {
            "artist": "urn:entity:artist",
            "music": "urn:entity:artist",
            "film": "urn:entity:movie",
            "movie": "urn:entity:movie",
            "book": "urn:entity:book",
            "tv": "urn:entity:tv_show",
        }
        label, sep, rest = name.partition(":")
        if sep and label.strip().casefold() in hints and rest.strip():
            return self._resolve(rest.strip(), entity_type=hints[label.strip().casefold()])
        return self._resolve(name)

    def resolve_place(self, name: str) -> tuple[str, str]:
        return self._resolve(name, entity_type="urn:entity:place")

    def rank(self, places: list[Place], taste_refs: Iterable[str]) -> TasteResults:
        return self.rank_with_context(places, taste_refs, failed_place=None)

    def rank_with_context(
        self,
        places: list[Place],
        taste_refs: Iterable[str],
        *,
        failed_place: str | None,
    ) -> TasteResults:
        refs = [x.strip() for x in taste_refs if x.strip()]
        if not refs and not failed_place:
            return TasteResults(
                [TasteResult(p.id, None, None, (), "qloo") for p in places],
                trace={
                    "status": "no_signals",
                    "insights_called": False,
                    "ranked_entity_count": 0,
                    "input_references": [],
                    "recognized_signals": [],
                    "failed_place_anchor": None,
                    "anchor_used": False,
                    "discovery_used": False,
                },
            )

        # The engine orders this pool using feasibility/fact quality/geography
        # before taste is considered. Qloo then ranks one shared shortlist, which
        # matches the official qloo_rank workflow and avoids spending quota on
        # every discovered Warsaw venue.
        qloo_places = places[:QLOO_MAX_RANK_OPTIONS]
        interests: list[tuple[str, str]] = []
        recognized_signals: list[dict[str, str]] = []
        unresolved_signals: list[dict[str, str]] = []
        for ref in refs:
            try:
                entity_id, resolved_name = self.resolve_interest(ref)
            except ValueError as exc:
                # Ambiguous cultural signals must not invalidate otherwise viable plans.
                # They are omitted from the live request and disclosed in the trace.
                unresolved_signals.append({"input": ref, "reason": str(exc)})
                continue
            interests.append((entity_id, resolved_name))
            recognized_signals.append(
                {"input": ref, "entity_id": entity_id, "name": resolved_name, "kind": "taste_reference"}
            )

        anchor_used = False
        anchor_error = None
        if failed_place:
            try:
                entity_id, resolved_name = self.resolve_place(failed_place)
                interests.append((entity_id, resolved_name))
                recognized_signals.append(
                    {"input": failed_place, "entity_id": entity_id, "name": resolved_name, "kind": "failed_place_anchor"}
                )
                anchor_used = True
            except ValueError as exc:
                # The failed venue remains excluded by the core engine even when
                # Qloo cannot resolve it as an optional taste anchor.
                anchor_error = str(exc)

        if not interests:
            # Without any resolved cultural input (or a valid optional anchor)
            # Insights cannot personalize this search. Do not burn up to ten
            # further calls trying to resolve venue IDs that cannot be ranked.
            return TasteResults(
                [TasteResult(p.id, None, None, (), "qloo") for p in places],
                trace={
                    "status": "no_coverage",
                    "insights_called": False,
                    "ranked_entity_count": 0,
                    "input_references": refs,
                    "recognized_signals": recognized_signals,
                    "failed_place_anchor": failed_place or None,
                    "anchor_used": False,
                    "anchor_error": anchor_error,
                    "unresolved_signals": unresolved_signals,
                    "unresolved_candidate_ids": [],
                    "candidate_entity_count": 0,
                    "discovery_used": False,
                },
            )
        resolved_place_ids: dict[str, str] = {}
        unresolved_candidates: list[str] = []
        for place in qloo_places:
            try:
                resolved_place_ids[place.id] = place.qloo_entity_id or self.resolve_place(place.name)[0]
            except ValueError:
                # Warsaw OSM venues are not guaranteed to exist in Qloo's catalog.
                # Do not silently associate a venue with a similarly named entity.
                unresolved_candidates.append(place.id)
        candidate_ids = list(dict.fromkeys(resolved_place_ids.values()))
        if not interests or not candidate_ids:
            return TasteResults(
                [TasteResult(p.id, None, None, (), "qloo") for p in places],
                trace={
                    "status": "no_coverage",
                    "insights_called": False,
                    "ranked_entity_count": 0,
                    "input_references": refs,
                    "recognized_signals": recognized_signals,
                    "failed_place_anchor": failed_place or None,
                    "anchor_used": anchor_used,
                    "anchor_error": anchor_error,
                    "unresolved_signals": unresolved_signals,
                    "unresolved_candidate_ids": unresolved_candidates,
                    "resolved_candidates": [
                        {"place_id": place_id, "entity_id": entity_id}
                        for place_id, entity_id in resolved_place_ids.items()
                    ],
                    "candidate_entity_count": len(candidate_ids),
                    "discovery_used": False,
                },
            )
        params = {
            "filter.type": "urn:entity:place",
            "signal.interests.entities": ",".join(entity_id for entity_id, _name_value in interests),
            "filter.results.entities": ",".join(candidate_ids),
            "feature.explainability": "true",
            "sort_by": "affinity",
            "take": len(candidate_ids),
        }
        payload = self.transport.get_json("/v2/insights", params)
        by_entity: dict[str, TasteResult] = {}
        for rank, row in enumerate(_entity_rows(payload), start=1):
            entity_id = _entity_id(row)
            if entity_id in candidate_ids:
                by_entity[entity_id] = TasteResult(
                    place_id=next(place_id for place_id, resolved_id in resolved_place_ids.items() if resolved_id == entity_id),
                    affinity=_affinity(row),
                    rank=rank,
                    evidence=_explainability_evidence(row, interests),
                    source="qloo",
                )
        return TasteResults(
            [
                (
                    by_entity.get(resolved_place_ids[p.id], TasteResult(p.id, None, None, (), "qloo"))
                    if p.id in resolved_place_ids
                    else TasteResult(p.id, None, None, (), "qloo")
                )
                for p in places
            ],
            trace={
                "status": "live" if by_entity else "no_coverage",
                "insights_called": True,
                "ranked_entity_count": len(by_entity),
                "input_references": refs,
                "recognized_signals": recognized_signals,
                "failed_place_anchor": failed_place or None,
                "anchor_used": anchor_used,
                "anchor_error": anchor_error,
                "unresolved_signals": unresolved_signals,
                "unresolved_candidate_ids": unresolved_candidates,
                "resolved_candidates": [
                    {"place_id": place_id, "entity_id": entity_id}
                    for place_id, entity_id in resolved_place_ids.items()
                ],
                "candidate_entity_count": len(candidate_ids),
                "discovery_used": False,
            },
        )

    def rank_pair_with_context(
        self, places: list[Place], first_refs: Iterable[str], second_refs: Iterable[str],
        *, failed_place: str | None,
    ) -> TasteResults:
        """Two independent insights rankings of the same operational pool.

        This policy compares *positions*, never merges raw affinity scores from
        different profiles. A pair recommendation is verified only when at least
        two distinct venues appear in both rankings. The existing outer job
        request scope and transport cache share venue lookups across profiles.
        """
        first_refs = tuple(ref for ref in first_refs if ref.strip())
        second_refs = tuple(ref for ref in second_refs if ref.strip())
        def no_pair(
            reason: str, first: TasteResults | None = None,
            second: TasteResults | None = None,
        ) -> TasteResults:
            a = dict(first.trace) if first is not None else {}
            b = dict(second.trace) if second is not None else {}
            return TasteResults(
                [TasteResult(p.id, None, None, (), "qloo") for p in places],
                trace={
                    "status": "no_coverage",
                    "pair_status": "insufficient_coverage",
                    "pair_reason": reason,
                    "input_references": list(first_refs),
                    "second_input_references": list(second_refs),
                    "recognized_signals": [
                        {**row, "profile": "A"} for row in a.get("recognized_signals", [])
                    ] + [
                        {**row, "profile": "B"} for row in b.get("recognized_signals", [])
                    ],
                    "unresolved_signals": [
                        {**row, "profile": "A"} for row in a.get("unresolved_signals", [])
                    ] + [
                        {**row, "profile": "B"} for row in b.get("unresolved_signals", [])
                    ],
                    "candidate_entity_count": max(a.get("candidate_entity_count", 0),
                                                  b.get("candidate_entity_count", 0)),
                    "ranked_entity_count": 0,
                    "insights_called": bool(a.get("insights_called") or b.get("insights_called")),
                    "profile_a_ranked_count": sum(x.rank is not None for x in first or []),
                    "profile_b_ranked_count": sum(x.rank is not None for x in second or []),
                    "discovery_used": False,
                },
            )

        if not first_refs or not second_refs:
            return no_pair("Two individual cultural profiles are required.")
        if len(first_refs) > 2 or len(second_refs) > 2:
            raise ValueError("Good for both supports up to two tastes per person.")
        # A failed-venue anchor is a shared logistical clue, not an individual
        # preference. Do not let it masquerade as either participant's tastes.
        a = self.rank_with_context(places, first_refs, failed_place=None)
        a_by_place = {x.place_id: x.rank for x in a if x.rank is not None}
        if a.trace.get("status") != "live" or len(a_by_place) < 2:
            return no_pair("Person A has fewer than two Qloo-ranked venues; no fair comparison was attempted.", a)
        b = self.rank_with_context(places, second_refs, failed_place=None)
        b_by_place = {x.place_id: x.rank for x in b if x.rank is not None}
        if b.trace.get("status") != "live" or len(b_by_place) < 2:
            return no_pair("Person B has fewer than two Qloo-ranked venues.", a, b)

        common_ids = set(a_by_place) & set(b_by_place)
        if len(common_ids) < 2:
            return no_pair("Fewer than two venues received Qloo ranks in both profiles.", a, b)
        ordered = sorted(
            common_ids,
            key=lambda p: (max(a_by_place[p], b_by_place[p]),
                           a_by_place[p] + b_by_place[p],
                           abs(a_by_place[p] - b_by_place[p]), p),
        )
        position = {place_id: rank for rank, place_id in enumerate(ordered, 1)}
        def ranked(p: Place) -> TasteResult:
            if p.id not in position:
                return TasteResult(p.id, None, None, (), "qloo")
            return TasteResult(
                p.id, None, position[p.id],
                (f"Person A Qloo position {a_by_place[p.id]}",
                 f"Person B Qloo position {b_by_place[p.id]}"),
                "qloo",
            )
        return TasteResults(
            [ranked(p) for p in places],
            trace={
                "status": "live",
                "pair_status": "verified",
                "pair_reason": (
                    "Fairness is an Unstuck minimax policy over two separate Qloo ranks, "
                    "not a Qloo probability of joint preference."
                ),
                "input_references": list(first_refs),
                "second_input_references": list(second_refs),
                "recognized_signals": [
                    {**row, "profile": "A"} for row in a.trace.get("recognized_signals", [])
                ] + [
                    {**row, "profile": "B"} for row in b.trace.get("recognized_signals", [])
                ],
                "unresolved_signals": [
                    {**row, "profile": "A"} for row in a.trace.get("unresolved_signals", [])
                ] + [
                    {**row, "profile": "B"} for row in b.trace.get("unresolved_signals", [])
                ],
                "candidate_entity_count": min(a.trace.get("candidate_entity_count", 0),
                                              b.trace.get("candidate_entity_count", 0)),
                "ranked_entity_count": len(common_ids),
                "insights_called": bool(a.trace.get("insights_called") and b.trace.get("insights_called")),
                "profile_a_ranked_count": len(a_by_place),
                "profile_b_ranked_count": len(b_by_place),
                "pair_positions": [
                    {"place_id": p, "person_a_rank": a_by_place[p],
                     "person_b_rank": b_by_place[p], "compromise_rank": position[p]}
                    for p in ordered[:QLOO_MAX_RANK_OPTIONS]
                ],
                "discovery_used": False,
            },
        )
