from __future__ import annotations

import json
import os
import time
import unicodedata
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
        max_network_calls: int = 40,
        cache_ttl_seconds: int = 300,
    ):
        self.api_key = (api_key if api_key is not None else os.environ.get("QLOO_API_KEY", "")).strip()
        self.base_url = base_url.rstrip("/")
        if not self.api_key:
            raise RuntimeError("BLOCKED_NO_API_KEY")
        if max_network_calls < 1:
            raise ValueError("max_network_calls must be at least 1")
        self.max_network_calls = max_network_calls
        self.network_calls = 0
        self.cache_ttl_seconds = max(0, cache_ttl_seconds)
        # Deliberately process-memory only: no Qloo output is persisted to disk.
        # This avoids building a local Qloo database and only deduplicates short-lived calls.
        self._cache: dict[str, tuple[float, dict]] = {}

    @staticmethod
    def _cache_key(path: str, params: dict[str, str | int | float] | None) -> str:
        return json.dumps([path, sorted((params or {}).items())], separators=(",", ":"), ensure_ascii=False)

    def clear_cache(self) -> None:
        self._cache.clear()

    def get_json(self, path: str, params: dict[str, str | int | float] | None = None) -> dict:
        if not path.startswith("/"):
            raise ValueError("path must start with /")
        cache_key = self._cache_key(path, params)
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] <= self.cache_ttl_seconds:
            return cached[1]
        if self.network_calls >= self.max_network_calls:
            raise RuntimeError("QLOO_CALL_BUDGET_EXHAUSTED")
        self.network_calls += 1
        query = urlencode(params or {})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        request = Request(url, headers={"X-Api-Key": self.api_key, "Accept": "application/json"})
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urlopen(request, timeout=12) as response:
                    raw = response.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise RuntimeError("Qloo response exceeded safety limit")
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise RuntimeError("Unexpected Qloo response")
                if self.cache_ttl_seconds:
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

    def _resolve(self, name: str, *, entity_type: str | None = None) -> tuple[str, str]:
        params: dict[str, str | int] = {"query": name, "take": 5}
        if entity_type:
            params["types"] = entity_type
        payload = self.transport.get_json("/search", params)
        rows = _entity_rows(payload)
        comparable = _comparable_name(name)
        exact = [
            (row, _entity_id(row), _name(row))
            for row in rows
            if _comparable_name(_name(row)) == comparable
            and (not entity_type or entity_type in _types(row))
        ]
        exact = [x for x in exact if x[1]]
        if len(exact) == 1:
            return exact[0][1], exact[0][2]
        if not rows:
            raise ValueError(f"Qloo could not resolve interest: {name}")
        options = ", ".join(_name(row) for row in rows[:3] if _name(row))
        raise ValueError(f"Ambiguous Qloo interest '{name}'. Matches: {options}")

    def resolve_interest(self, name: str) -> tuple[str, str]:
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
                    "status": "live",
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
        for ref in refs:
            entity_id, resolved_name = self.resolve_interest(ref)
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

        resolved_place_ids: dict[str, str] = {}
        for place in qloo_places:
            resolved_place_ids[place.id] = place.qloo_entity_id or self.resolve_place(place.name)[0]
        candidate_ids = list(resolved_place_ids.values())
        if not interests:
            return TasteResults(
                [TasteResult(p.id, None, None, (), "qloo") for p in places],
                trace={
                    "status": "live",
                    "input_references": refs,
                    "recognized_signals": recognized_signals,
                    "failed_place_anchor": failed_place or None,
                    "anchor_used": anchor_used,
                    "anchor_error": anchor_error,
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
                "status": "live",
                "input_references": refs,
                "recognized_signals": recognized_signals,
                "failed_place_anchor": failed_place or None,
                "anchor_used": anchor_used,
                "anchor_error": anchor_error,
                "candidate_entity_count": len(candidate_ids),
                "discovery_used": False,
            },
        )
