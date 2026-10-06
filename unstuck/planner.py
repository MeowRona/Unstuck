from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from unstuck.geocoding import address_index
from unstuck.models import Place
from unstuck.origins import resolve_origin


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "planner_warsaw.json"
WARSAW_TZ = ZoneInfo("Europe/Warsaw")
DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _clock(text: str) -> tuple[int, int]:
    hour, minute = str(text).split(":", 1)
    return int(hour), int(minute)


def _dt(day: date, clock: str) -> datetime:
    hour, minute = _clock(clock)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=WARSAW_TZ)


def _minutes_between(a: tuple[float, float], b: tuple[float, float], mode: str) -> int:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    km = 6371.0 * 2 * math.atan2(math.sqrt(h), math.sqrt(max(0.0, 1 - h)))
    if mode == "walk":
        return max(2, math.ceil(km / 4.6 * 60 * 1.12))
    return max(6, math.ceil(5 + km * 3.2))


def _money(raw: dict[str, Any] | None, people: int) -> dict[str, Any]:
    raw = raw or {}
    minimum = raw.get("min")
    maximum = raw.get("max")
    basis = raw.get("basis") or "per_person"
    if minimum is not None:
        minimum = float(minimum)
    if maximum is not None:
        maximum = float(maximum)
    if basis == "per_person":
        minimum = minimum * people if minimum is not None else None
        maximum = maximum * people if maximum is not None else None
    return {
        "status": str(raw.get("status") or "unknown"),
        "currency": str(raw.get("currency") or "PLN"),
        "min": minimum,
        "max": maximum,
        "basis": basis,
        "note": str(raw.get("note") or ""),
    }


def _weekday(day: date) -> str:
    return DAY_KEYS[day.weekday()]


def _source_meta(row: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = sources.get(str(row.get("source_id") or ""), {})
    return {
        "name": source.get("name"),
        "url": row.get("source_url") or source.get("url"),
        "checked_at": row.get("checked_at"),
        "ingestion": source.get("ingestion"),
    }


@dataclass(frozen=True)
class PlannerBrief:
    date: str
    start_time: str
    end_time: str
    origin: str
    origin_lat: float
    origin_lon: float
    return_required: bool
    return_origin: str
    return_lat: float
    return_lon: float
    people: int
    budget_total: float
    activity_count: int
    pace: str
    travel_mode: str
    event_buffer_minutes: int
    include_meal: bool
    categories: tuple[str, ...]
    interests: tuple[str, ...]
    taste_refs: tuple[str, ...]
    must_include_ids: tuple[str, ...]
    locked_ids: tuple[str, ...]
    excluded_ids: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PlannerBrief":
        try:
            day = date.fromisoformat(str(payload.get("date") or ""))
        except ValueError as exc:
            raise ValueError("date must use YYYY-MM-DD") from exc

        def time_value(name: str, default: str) -> str:
            raw = str(payload.get(name) or default).strip()
            try:
                _clock(raw)
            except Exception as exc:
                raise ValueError(f"{name} must use HH:MM") from exc
            return raw

        start_time = time_value("start_time", "11:00")
        end_time = time_value("end_time", "22:00")
        start_dt = _dt(day, start_time)
        end_dt = _dt(day, end_time)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        if end_dt - start_dt > timedelta(hours=20):
            raise ValueError("planning window must be no longer than 20 hours")

        origin_name = str(payload.get("origin") or "Warsaw Central").strip() or "Warsaw Central"
        origin_lat = payload.get("origin_lat")
        origin_lon = payload.get("origin_lon")
        if origin_lat is None or origin_lon is None:
            origin_lat, origin_lon = resolve_origin(origin_name)
        else:
            origin_lat, origin_lon = float(origin_lat), float(origin_lon)

        return_required = bool(payload.get("return_required", True))
        return_name = str(payload.get("return_origin") or origin_name).strip() or origin_name
        return_lat = payload.get("return_lat")
        return_lon = payload.get("return_lon")
        if return_lat is None or return_lon is None:
            if return_name == origin_name:
                return_lat, return_lon = origin_lat, origin_lon
            else:
                return_lat, return_lon = resolve_origin(return_name)
        else:
            return_lat, return_lon = float(return_lat), float(return_lon)

        people = int(payload.get("people", 2))
        if not 1 <= people <= 12:
            raise ValueError("people must be between 1 and 12")
        budget = float(payload.get("budget_total", 300))
        if budget <= 0:
            raise ValueError("budget_total must be positive")
        activity_count = int(payload.get("activity_count", 3))
        if not 1 <= activity_count <= 4:
            raise ValueError("activity_count must be between 1 and 4")
        pace = str(payload.get("pace") or "balanced").strip().lower()
        if pace not in {"easy", "balanced", "full"}:
            raise ValueError("pace must be easy, balanced, or full")
        travel_mode = str(payload.get("travel_mode") or "transit").strip().lower()
        if travel_mode not in {"walk", "transit"}:
            raise ValueError("travel_mode must be walk or transit")

        def strings(name: str) -> tuple[str, ...]:
            raw = payload.get(name) or []
            if isinstance(raw, str):
                raw = [x.strip() for x in raw.split(",")]
            return tuple(dict.fromkeys(str(x).strip() for x in raw if str(x).strip()))

        return cls(
            date=day.isoformat(),
            start_time=start_time,
            end_time=end_time,
            origin=origin_name,
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            return_required=return_required,
            return_origin=return_name,
            return_lat=return_lat,
            return_lon=return_lon,
            people=people,
            budget_total=budget,
            activity_count=activity_count,
            pace=pace,
            travel_mode=travel_mode,
            event_buffer_minutes=max(0, min(60, int(payload.get("event_buffer_minutes", 15)))),
            include_meal=bool(payload.get("include_meal", True)),
            categories=strings("categories"),
            interests=strings("interests"),
            taste_refs=strings("taste_refs"),
            must_include_ids=strings("must_include_ids"),
            locked_ids=strings("locked_ids"),
            excluded_ids=strings("excluded_ids"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "origin": self.origin,
            "origin_lat": self.origin_lat,
            "origin_lon": self.origin_lon,
            "return_required": self.return_required,
            "return_origin": self.return_origin,
            "return_lat": self.return_lat,
            "return_lon": self.return_lon,
            "people": self.people,
            "budget_total": self.budget_total,
            "activity_count": self.activity_count,
            "pace": self.pace,
            "travel_mode": self.travel_mode,
            "event_buffer_minutes": self.event_buffer_minutes,
            "include_meal": self.include_meal,
            "categories": list(self.categories),
            "interests": list(self.interests),
            "taste_refs": list(self.taste_refs),
            "must_include_ids": list(self.must_include_ids),
            "locked_ids": list(self.locked_ids),
            "excluded_ids": list(self.excluded_ids),
        }


class PlannerCatalog:
    def __init__(self, places: list[Place], path: Path = DATA_PATH):
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.payload = payload
        self.sources = {str(row["id"]): row for row in payload.get("sources", [])}
        self.venues: dict[str, dict[str, Any]] = {}
        for raw in payload.get("venues", []):
            row = dict(raw)
            local = address_index.lookup(str(row.get("address") or ""))
            if local:
                row["lat"] = local["lat"]
                row["lon"] = local["lon"]
                row["location_source"] = {
                    "name": local.get("source"),
                    "url": local.get("source_url"),
                    "checked_at": local.get("checked_at"),
                }
            self.venues[str(row["id"])] = row
        self.attractions = [dict(row) for row in payload.get("attractions", [])]
        self.events = self._dedupe_events([dict(row) for row in payload.get("events", [])])
        self.places = places
        self.restaurant_rows = self._restaurant_rows()

    @staticmethod
    def _dedupe_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str, str]] = set()
        out: list[dict[str, Any]] = []
        for row in rows:
            key = (
                " ".join(str(row.get("title") or "").casefold().split()),
                str(row.get("date") or ""),
                str(row.get("start_time") or ""),
                str(row.get("venue_id") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        return out

    def _restaurant_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        strong = [
            p for p in self.places
            if p.category == "restaurant"
            and p.price.status in {"confirmed", "fixture"}
            and p.hours_status in {"confirmed", "fixture"}
        ]
        for place in strong[:12]:
            rows.append(
                {
                    "id": f"restaurant:{place.id}",
                    "kind": "restaurant",
                    "title": place.name,
                    "category": "restaurant",
                    "description": place.source_note or "Restaurant from the existing Unstuck catalog.",
                    "venue": {
                        "id": f"place:{place.id}",
                        "name": place.name,
                        "address": place.address,
                        "lat": place.lat,
                        "lon": place.lon,
                    },
                    "duration_minutes_estimate": 75,
                    "hours": {key: [list(x) for x in value] for key, value in place.hours.items()},
                    "date_exceptions": {key: [list(x) for x in value] for key, value in place.date_exceptions.items()},
                    "hours_status": place.hours_status,
                    "price": {
                        "status": place.price.status,
                        "currency": place.price.unit,
                        "min": place.price.minimum,
                        "max": place.price.maximum,
                        "basis": place.price.basis or "per_person",
                        "note": "",
                    },
                    "availability": "unknown",
                    "source": {
                        "name": "Existing Unstuck restaurant catalog",
                        "url": place.hours_source_url or place.price.source_url or place.location_source_url,
                        "checked_at": place.hours_checked_at or place.price.checked_at or place.location_checked_at,
                        "ingestion": "existing_catalog",
                    },
                    "tags": list(place.taste_tags) + list(place.ambience),
                }
            )
        return rows

    def _venue(self, venue_id: str) -> dict[str, Any]:
        row = self.venues.get(venue_id)
        if not row:
            raise ValueError(f"Unknown planner venue: {venue_id}")
        return dict(row)

    def public_catalog(self, selected_date: str | None = None) -> dict[str, Any]:
        day = date.fromisoformat(selected_date) if selected_date else None
        items = self.activities_for_date(day) if day else self.discovery_rows()
        return {
            "schema_version": self.payload.get("schema_version", 1),
            "city": self.payload.get("city", "Warsaw"),
            "timezone": self.payload.get("timezone", "Europe/Warsaw"),
            "checked_at": self.payload.get("checked_at"),
            "coverage": self.payload.get("coverage"),
            "sources": list(self.sources.values()),
            "items": items,
            "event_dates": sorted({str(row.get("date")) for row in self.events if row.get("date")}),
        }

    def discovery_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in self.attractions:
            venue = self._venue(str(row["venue_id"]))
            rows.append(self._public_activity({**row, "kind": "attraction", "venue": venue}))
        for row in self.events:
            venue = self._venue(str(row["venue_id"]))
            rows.append(self._public_activity({**row, "kind": "event", "venue": venue}))
        rows.extend(self.restaurant_rows)
        return rows

    def activities_for_date(self, day: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in self.attractions:
            venue = self._venue(str(row["venue_id"]))
            activity = {**row, "kind": "attraction", "venue": venue}
            activity["date_status"] = self._attraction_date_status(activity, day)
            rows.append(self._public_activity(activity))
        for row in self.events:
            if str(row.get("date")) != day.isoformat():
                continue
            venue = self._venue(str(row["venue_id"]))
            rows.append(self._public_activity({**row, "kind": "event", "venue": venue}))
        for row in self.restaurant_rows:
            item = dict(row)
            item["date_status"] = self._restaurant_date_status(item, day)
            rows.append(self._public_activity(item))
        return rows

    def _public_activity(self, row: dict[str, Any]) -> dict[str, Any]:
        source = row.get("source") or _source_meta(row, self.sources)
        venue = dict(row.get("venue") or self._venue(str(row["venue_id"])))
        schedulable = bool(row.get("schedulable", True))
        if venue.get("lat") is None or venue.get("lon") is None:
            schedulable = False
        return {
            "id": str(row["id"]),
            "series_id": row.get("series_id"),
            "kind": str(row.get("kind") or "attraction"),
            "title": str(row.get("title") or ""),
            "category": str(row.get("category") or "other"),
            "description": str(row.get("description") or ""),
            "venue": venue,
            "date": row.get("date"),
            "start_time": row.get("start_time"),
            "doors_time": row.get("doors_time"),
            "end_time": row.get("end_time"),
            "end_status": row.get("end_status"),
            "flexible_visit_window": bool(row.get("flexible_visit_window", False)),
            "duration_minutes_estimate": row.get("duration_minutes_estimate") or row.get("planning_duration_minutes"),
            "duration_status": row.get("planning_duration_status") or "estimate",
            "last_entry_minutes_before_close": row.get("last_entry_minutes_before_close"),
            "weekly_hours": row.get("weekly_hours") or {},
            "closed_dates": list(row.get("closed_dates") or []),
            "hours": row.get("hours") or {},
            "date_exceptions": row.get("date_exceptions") or {},
            "hours_status": row.get("hours_status"),
            "price": row.get("price") or {"status": "unknown", "currency": "PLN"},
            "availability": str(row.get("availability") or "unknown"),
            "status": str(row.get("status") or "planned"),
            "schedulable": schedulable,
            "unschedulable_reason": row.get("unschedulable_reason") or (
                "Venue coordinates are unavailable in the bundled Warsaw address index." if not schedulable else None
            ),
            "source": source,
            "info_url": row.get("info_url") or source.get("url"),
            "ticket_url": row.get("ticket_url"),
            "checked_at": row.get("checked_at") or source.get("checked_at"),
            "tags": list(row.get("tags") or []),
            "date_status": row.get("date_status"),
        }

    @staticmethod
    def _attraction_date_status(row: dict[str, Any], day: date) -> str:
        if day.isoformat() in set(row.get("closed_dates") or []):
            return "closed"
        windows = (row.get("weekly_hours") or {}).get(_weekday(day), [])
        return "open" if windows else "closed"

    @staticmethod
    def _restaurant_date_status(row: dict[str, Any], day: date) -> str:
        exceptions = row.get("date_exceptions") or {}
        if day.isoformat() in exceptions:
            return "open" if exceptions[day.isoformat()] else "closed"
        windows = (row.get("hours") or {}).get(str(day.weekday()), [])
        if windows:
            return "open"
        return "unknown" if row.get("hours_status") not in {"confirmed", "fixture"} else "closed"

    def raw_by_id(self, activity_id: str) -> dict[str, Any] | None:
        for row in self.discovery_rows():
            if row["id"] == activity_id:
                return row
        return None


class DayPlanner:
    def __init__(self, catalog: PlannerCatalog):
        self.catalog = catalog

    def generate(
        self,
        brief: PlannerBrief,
        *,
        preferred_ids: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        day = date.fromisoformat(brief.date)
        items = self.catalog.activities_for_date(day)
        eligible, blockers = self._eligible(items, brief)
        requested = brief.activity_count
        variants: list[dict[str, Any]] = []
        used_count = requested
        for count in range(requested, 0, -1):
            variants = self._variants(eligible, brief, count, preferred_ids=preferred_ids)
            if variants:
                used_count = count
                break

        if not variants:
            return {
                "brief": brief.to_dict(),
                "plans": [],
                "result_status": "conflict",
                "requested_activity_count": requested,
                "planned_activity_count": 0,
                "explanation": self._no_plan_explanation(blockers, brief),
                "taste_status": "not_live" if brief.taste_refs else "not_requested",
                "coverage": self.catalog.payload.get("coverage"),
            }

        explanation = None
        if used_count < requested:
            explanation = (
                f"Only {used_count} activity{'ies' if used_count != 1 else 'y'} fit the current window "
                f"without breaking locked time/date conditions; requested {requested}."
            )
        return {
            "brief": brief.to_dict(),
            "plans": variants[:3],
            "result_status": "planned",
            "requested_activity_count": requested,
            "planned_activity_count": used_count,
            "explanation": explanation,
            "taste_status": "not_live" if brief.taste_refs else "not_requested",
            "taste_note": (
                "Taste matching not live yet. These variants are ordered by feasibility, explicit interests, "
                "preservation during repair, and travel—not by Qloo."
            ),
            "coverage": self.catalog.payload.get("coverage"),
        }

    def repair(self, plan: dict[str, Any], brief: PlannerBrief, removed_id: str) -> dict[str, Any]:
        original_ids = tuple(str(item["activity_id"]) for item in plan.get("items", []))
        locked_ids = tuple(dict.fromkeys([*brief.locked_ids, *plan.get("locked_ids", [])]))
        if removed_id in locked_ids:
            raise ValueError("Remove the lock before replacing this activity")
        patched = PlannerBrief(
            **{
                **brief.__dict__,
                "excluded_ids": tuple(dict.fromkeys([*brief.excluded_ids, removed_id])),
                "locked_ids": locked_ids,
                "must_include_ids": tuple(dict.fromkeys([*brief.must_include_ids, *locked_ids])),
            }
        )
        result = self.generate(patched, preferred_ids=tuple(x for x in original_ids if x != removed_id))
        for candidate in result.get("plans", []):
            new_ids = [item["activity_id"] for item in candidate["items"]]
            kept = [x for x in original_ids if x != removed_id and x in new_ids]
            added = [x for x in new_ids if x not in original_ids]
            candidate["repair"] = {
                "removed": removed_id,
                "kept_ids": kept,
                "added_ids": added,
                "locked_ids": list(locked_ids),
                "changed_count": len(added),
            }
        return result

    def _eligible(self, items: list[dict[str, Any]], brief: PlannerBrief) -> tuple[list[dict[str, Any]], list[str]]:
        out: list[dict[str, Any]] = []
        blockers: list[str] = []
        required = set(brief.must_include_ids) | set(brief.locked_ids)
        excluded = set(brief.excluded_ids)
        known_ids = {row["id"] for row in items}
        for req in required:
            if req not in known_ids:
                blockers.append(f"Required item {req} is not available on {brief.date}.")
        for row in items:
            if row["id"] in excluded:
                continue
            if not row.get("schedulable", True):
                if row["id"] in required:
                    blockers.append(f"{row['title']} cannot be scheduled: {row.get('unschedulable_reason') or 'missing time data'}.")
                continue
            if row.get("status") == "cancelled":
                if row["id"] in required:
                    blockers.append(f"{row['title']} is marked cancelled.")
                continue
            if row.get("availability") == "sold_out":
                if row["id"] in required:
                    blockers.append(f"{row['title']} is marked sold out.")
                continue
            if row.get("date_status") == "closed":
                if row["id"] in required:
                    blockers.append(f"{row['title']} is closed on {brief.date}.")
                continue
            if brief.categories and row["category"] not in brief.categories and row["kind"] != "restaurant":
                continue
            out.append(row)
        return out, blockers

    def _variants(
        self,
        items: list[dict[str, Any]],
        brief: PlannerBrief,
        count: int,
        *,
        preferred_ids: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        required = set(brief.must_include_ids) | set(brief.locked_ids)
        if len(required) > count:
            return []
        restaurants = [x for x in items if x["kind"] == "restaurant"]
        nonrestaurants = [x for x in items if x["kind"] != "restaurant"]
        candidate_pool = nonrestaurants[:18] + restaurants[:8]
        plans: list[dict[str, Any]] = []
        for combo in itertools.combinations(candidate_pool, count):
            ids = {row["id"] for row in combo}
            if not required.issubset(ids):
                continue
            if brief.include_meal and not any(row["kind"] == "restaurant" for row in combo):
                continue
            for ordered in itertools.permutations(combo):
                scheduled = self._schedule(list(ordered), brief)
                if not scheduled:
                    continue
                plan = self._plan_payload(scheduled, brief, preferred_ids=preferred_ids)
                if plan["known_cost_max"] is not None and plan["unknown_cost_components"] == 0:
                    if plan["known_cost_max"] > brief.budget_total:
                        continue
                elif plan["known_cost_min"] is not None and plan["known_cost_min"] > brief.budget_total:
                    continue
                plans.append(plan)
        plans.sort(
            key=lambda row: (
                -row["preserved_preferred_count"],
                0 if row["feasibility"] == "confirmed" else 1,
                -row["interest_match_count"],
                row["total_travel_minutes"],
                row["known_cost_max"] if row["known_cost_max"] is not None else float("inf"),
                row["id"],
            )
        )
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for plan in plans:
            signature = tuple(item["activity_id"] for item in plan["items"])
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(plan)
            if len(unique) >= 3:
                break
        return unique

    def _schedule(self, ordered: list[dict[str, Any]], brief: PlannerBrief) -> list[dict[str, Any]] | None:
        day = date.fromisoformat(brief.date)
        start_dt = _dt(day, brief.start_time)
        end_dt = _dt(day, brief.end_time)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        current = start_dt
        coords = (brief.origin_lat, brief.origin_lon)
        scheduled: list[dict[str, Any]] = []
        for row in ordered:
            venue = row["venue"]
            if venue.get("lat") is None or venue.get("lon") is None:
                return None
            target = (float(venue["lat"]), float(venue["lon"]))
            travel = _minutes_between(coords, target, brief.travel_mode)
            arrival = current + timedelta(minutes=travel)
            slot = self._slot(row, day, arrival, brief.pace, brief.event_buffer_minutes)
            if slot is None:
                return None
            activity_start, activity_end, waiting, window_end, latest_entry = slot
            if activity_end > end_dt:
                return None
            scheduled.append(
                {
                    "activity": row,
                    "travel_minutes": travel,
                    "travel_status": "estimate",
                    "depart": current,
                    "arrive": arrival,
                    "wait_minutes": waiting,
                    "start": activity_start,
                    "end": activity_end,
                    "window_end": window_end,
                    "latest_entry": latest_entry,
                    "from_coords": coords,
                    "to_coords": target,
                }
            )
            current = activity_end
            coords = target

        if brief.return_required:
            return_target = (brief.return_lat, brief.return_lon)
            travel = _minutes_between(coords, return_target, brief.travel_mode)
            back = current + timedelta(minutes=travel)
            if back > end_dt:
                return None
            scheduled.append(
                {
                    "activity": None,
                    "travel_minutes": travel,
                    "travel_status": "estimate",
                    "depart": current,
                    "arrive": back,
                    "wait_minutes": 0,
                    "start": None,
                    "end": None,
                    "from_coords": coords,
                    "to_coords": return_target,
                    "return_leg": True,
                }
            )
        return scheduled

    def _slot(
        self,
        row: dict[str, Any],
        day: date,
        arrival: datetime,
        pace: str,
        event_buffer_minutes: int = 0,
    ) -> tuple[datetime, datetime, int, datetime | None, datetime | None] | None:
        duration = self._duration(row, pace)
        if row["kind"] == "event" and row.get("start_time") and not row.get("flexible_visit_window"):
            start = _dt(day, str(row["start_time"]))
            latest_arrival = start - timedelta(minutes=max(0, event_buffer_minutes))
            if arrival > latest_arrival:
                return None
            waiting = int((start - arrival).total_seconds() // 60)
            end = _dt(day, str(row["end_time"])) if row.get("end_time") else start + timedelta(minutes=duration)
            if end <= start:
                end += timedelta(days=1)
            return start, end, waiting, None, start

        windows = self._windows(row, day)
        if not windows:
            return None
        for open_time, close_time, last_entry in windows:
            start = max(arrival, open_time)
            if start > last_entry:
                continue
            end = start + timedelta(minutes=duration)
            if end <= close_time:
                return start, end, max(0, int((start - arrival).total_seconds() // 60)), close_time, last_entry
        return None

    @staticmethod
    def _duration(row: dict[str, Any], pace: str) -> int:
        base = int(row.get("duration_minutes_estimate") or 75)
        if row["kind"] == "event" and not row.get("flexible_visit_window"):
            return base
        factor = {"easy": 1.2, "balanced": 1.0, "full": 0.8}[pace]
        return max(30, int(round(base * factor / 5) * 5))

    @staticmethod
    def _windows(row: dict[str, Any], day: date) -> list[tuple[datetime, datetime, datetime]]:
        if row["kind"] == "event":
            if row.get("start_time") and row.get("end_time") and row.get("flexible_visit_window"):
                start = _dt(day, str(row["start_time"]))
                end = _dt(day, str(row["end_time"]))
                if end <= start:
                    end += timedelta(days=1)
                return [(start, end, end)]
            return []
        if row["kind"] == "attraction":
            windows = (row.get("weekly_hours") or {}).get(_weekday(day), [])
            last_before = int(row.get("last_entry_minutes_before_close") or 0)
        else:
            exceptions = row.get("date_exceptions") or {}
            windows = exceptions.get(day.isoformat())
            if windows is None:
                windows = (row.get("hours") or {}).get(str(day.weekday()), [])
            last_before = 0
            if not windows and row.get("hours_status") not in {"confirmed", "fixture"}:
                windows = [["11:00", "23:00"]]
        out: list[tuple[datetime, datetime, datetime]] = []
        for start_clock, end_clock in windows or []:
            start = _dt(day, str(start_clock))
            end = _dt(day, str(end_clock))
            if end <= start:
                end += timedelta(days=1)
            out.append((start, end, end - timedelta(minutes=last_before)))
        return out

    def _plan_payload(
        self,
        scheduled: list[dict[str, Any]],
        brief: PlannerBrief,
        *,
        preferred_ids: tuple[str, ...],
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        travel_legs: list[dict[str, Any]] = []
        known_min = 0.0
        known_max = 0.0
        has_known_cost = False
        unknown_cost = 0
        checks: list[str] = []
        interest_match_count = 0
        total_travel = 0
        preferred = set(preferred_ids)
        preserved = 0
        for step in scheduled:
            total_travel += int(step["travel_minutes"])
            if step.get("return_leg"):
                travel_legs.append(
                    {
                        "from": "last activity",
                        "to": brief.return_origin,
                        "depart": step["depart"].strftime("%H:%M"),
                        "arrive": step["arrive"].strftime("%H:%M"),
                        "minutes": step["travel_minutes"],
                        "status": step["travel_status"],
                        "mode": brief.travel_mode,
                    }
                )
                continue
            row = step["activity"]
            price = _money(row.get("price"), brief.people)
            if price["min"] is None or price["max"] is None:
                unknown_cost += 1
                checks.append(f"Price for {row['title']} is unknown.")
            else:
                has_known_cost = True
                known_min += price["min"]
                known_max += price["max"]
            if row.get("availability") == "unknown" and row["kind"] == "event":
                checks.append(f"Ticket availability for {row['title']} is not confirmed.")
            if row.get("end_status") == "unknown" and row["kind"] == "event":
                checks.append(f"End time for {row['title']} is unknown; the timeline uses a planning estimate.")
            if row["kind"] == "restaurant" and row.get("hours_status") not in {"confirmed", "fixture"}:
                checks.append(f"Opening hours for {row['title']} need verification.")
            tags = {str(x).casefold() for x in row.get("tags", [])}
            tags.add(str(row.get("category") or "").casefold())
            matches = [interest for interest in brief.interests if interest.casefold() in tags]
            interest_match_count += len(matches)
            if row["id"] in preferred:
                preserved += 1
            item = {
                "activity_id": row["id"],
                "kind": row["kind"],
                "title": row["title"],
                "category": row["category"],
                "description": row["description"],
                "venue": row["venue"],
                "start": step["start"].strftime("%Y-%m-%dT%H:%M:%S%z"),
                "end": step["end"].strftime("%Y-%m-%dT%H:%M:%S%z"),
                "display_start": step["start"].strftime("%H:%M"),
                "display_end": step["end"].strftime("%H:%M"),
                "duration_minutes": int((step["end"] - step["start"]).total_seconds() // 60),
                "duration_status": row.get("duration_status") or "estimate",
                "fixed_time": bool(row["kind"] == "event" and row.get("start_time") and not row.get("flexible_visit_window")),
                "source": row.get("source"),
                "info_url": row.get("info_url"),
                "ticket_url": row.get("ticket_url"),
                "availability": row.get("availability"),
                "event_status": row.get("status"),
                "price": price,
                "checks": [],
                "interest_matches": matches,
                "doors_time": row.get("doors_time"),
                "source_event_end_status": row.get("end_status"),
                "visit_window_end": step["window_end"].isoformat() if step.get("window_end") else None,
                "latest_entry": step["latest_entry"].isoformat() if step.get("latest_entry") else None,
            }
            if row.get("end_status") == "unknown" and row["kind"] == "event":
                item["checks"].append("Actual event end time is unknown.")
            if price["status"] == "unknown":
                item["checks"].append("Price is unknown.")
            if row.get("availability") == "unknown" and row["kind"] == "event":
                item["checks"].append("Ticket availability is unknown.")
            items.append(item)
            travel_legs.append(
                {
                    "from": brief.origin if len(items) == 1 else items[-2]["title"],
                    "to": row["title"],
                    "depart": step["depart"].strftime("%H:%M"),
                    "arrive": step["arrive"].strftime("%H:%M"),
                    "minutes": step["travel_minutes"],
                    "status": step["travel_status"],
                    "mode": brief.travel_mode,
                    "wait_minutes": step["wait_minutes"],
                }
            )

        if unknown_cost:
            checks.append(
                f"{unknown_cost} cost component{'s are' if unknown_cost != 1 else ' is'} unknown, "
                "so the total budget cannot be guaranteed."
            )
        feasibility = "requires_checking" if checks else "confirmed"
        signature = "|".join([brief.date, *[x["activity_id"] for x in items]])
        plan_id = "plan:" + hashlib.sha1(signature.encode("utf-8")).hexdigest()[:14]
        return {
            "id": plan_id,
            "schema_version": 1,
            "date": brief.date,
            "timezone": "Europe/Warsaw",
            "items": items,
            "travel_legs": travel_legs,
            "total_travel_minutes": total_travel,
            "known_cost_min": round(known_min, 2) if has_known_cost else None,
            "known_cost_max": round(known_max, 2) if has_known_cost else None,
            "currency": "PLN",
            "unknown_cost_components": unknown_cost,
            "budget_total": brief.budget_total,
            "feasibility": feasibility,
            "checks": list(dict.fromkeys(checks)),
            "interest_match_count": interest_match_count,
            "preserved_preferred_count": preserved,
            "taste_status": "not_live" if brief.taste_refs else "not_requested",
            "taste_note": "Taste matching not live yet; Qloo was not called for this plan.",
            "locked_ids": list(brief.locked_ids),
            "route_status": "estimated",
            "start_time": brief.start_time,
            "end_time": brief.end_time,
            "return_required": brief.return_required,
            "return_origin": brief.return_origin if brief.return_required else None,
            "event_buffer_minutes": brief.event_buffer_minutes,
        }

    @staticmethod
    def _no_plan_explanation(blockers: list[str], brief: PlannerBrief) -> list[str]:
        rows = list(blockers)
        if not rows:
            rows.append(
                "No sequence fits the selected date/time window after travel, activity duration, fixed event times, and return."
            )
            if brief.activity_count > 1:
                rows.append("Try fewer activities, a wider time window, or a different must-do item.")
        return rows


def route_check_plan(
    plan: dict[str, Any],
    brief: PlannerBrief,
    route_func: Callable[[tuple[float, float], tuple[float, float], datetime, str], dict[str, Any]],
) -> dict[str, Any]:
    day = date.fromisoformat(brief.date)
    end_limit = _dt(day, brief.end_time)
    start = _dt(day, brief.start_time)
    if end_limit <= start:
        end_limit += timedelta(days=1)
    current = start
    coords = (brief.origin_lat, brief.origin_lon)
    checked_items: list[dict[str, Any]] = []
    legs: list[dict[str, Any]] = []
    conflicts: list[str] = []
    checks = list(plan.get("checks", []))
    for original in plan.get("items", []):
        target = (float(original["venue"]["lat"]), float(original["venue"]["lon"]))
        route = route_func(coords, target, current, brief.travel_mode)
        minutes = int(route["duration_minutes"])
        arrival = current + timedelta(minutes=minutes)
        planned_start = datetime.fromisoformat(original["start"])
        if planned_start.tzinfo is None:
            planned_start = planned_start.replace(tzinfo=WARSAW_TZ)
        fixed = bool(original.get("fixed_time"))
        if fixed:
            if arrival > planned_start:
                conflicts.append(f"Checked route reaches {original['title']} after its fixed start.")
                actual_start = planned_start
            else:
                actual_start = planned_start
        else:
            actual_start = max(arrival, planned_start)
        duration = int(original["duration_minutes"])
        actual_end = actual_start + timedelta(minutes=duration)
        latest_entry = datetime.fromisoformat(original["latest_entry"]) if original.get("latest_entry") else None
        visit_window_end = datetime.fromisoformat(original["visit_window_end"]) if original.get("visit_window_end") else None
        if latest_entry is not None and latest_entry.tzinfo is None:
            latest_entry = latest_entry.replace(tzinfo=WARSAW_TZ)
        if visit_window_end is not None and visit_window_end.tzinfo is None:
            visit_window_end = visit_window_end.replace(tzinfo=WARSAW_TZ)
        if not fixed and latest_entry is not None and actual_start > latest_entry:
            conflicts.append(
                f"Checked route reaches {original['title']} after its last accepted entry time."
            )
        if not fixed and visit_window_end is not None and actual_end > visit_window_end:
            conflicts.append(
                f"Checked route pushes {original['title']} past its available opening window."
            )
        item = dict(original)
        item.update(
            {
                "start": actual_start.isoformat(),
                "end": actual_end.isoformat(),
                "display_start": actual_start.strftime("%H:%M"),
                "display_end": actual_end.strftime("%H:%M"),
            }
        )
        checked_items.append(item)
        legs.append(
            {
                "from": brief.origin if not checked_items[:-1] else checked_items[-2]["title"],
                "to": original["title"],
                "depart": current.strftime("%H:%M"),
                "arrive": arrival.strftime("%H:%M"),
                "minutes": minutes,
                "status": "checked",
                "mode": brief.travel_mode,
                "source": route.get("source"),
                "scheduled": route.get("scheduled"),
                "realtime": route.get("realtime", False),
                "geometry": route.get("geometry"),
                "legs": route.get("legs"),
            }
        )
        current = actual_end
        coords = target

    if brief.return_required and checked_items:
        target = (brief.return_lat, brief.return_lon)
        route = route_func(coords, target, current, brief.travel_mode)
        minutes = int(route["duration_minutes"])
        back = current + timedelta(minutes=minutes)
        legs.append(
            {
                "from": checked_items[-1]["title"],
                "to": brief.return_origin,
                "depart": current.strftime("%H:%M"),
                "arrive": back.strftime("%H:%M"),
                "minutes": minutes,
                "status": "checked",
                "mode": brief.travel_mode,
                "source": route.get("source"),
                "scheduled": route.get("scheduled"),
                "realtime": route.get("realtime", False),
                "geometry": route.get("geometry"),
                "legs": route.get("legs"),
                "return_leg": True,
            }
        )
        if back > end_limit:
            conflicts.append(
                f"Checked return arrives at {back.strftime('%H:%M')}, after the locked {brief.end_time} limit."
            )
    elif checked_items and checked_items[-1]["end"] > end_limit.isoformat():
        conflicts.append("Checked timeline ends after the selected planning window.")

    checked = dict(plan)
    checked["items"] = checked_items
    checked["travel_legs"] = legs
    checked["total_travel_minutes"] = sum(int(x["minutes"]) for x in legs)
    checked["route_status"] = "checked"
    checked["route_checked_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    checked["route_conflicts"] = conflicts
    checked["feasibility"] = "conflict" if conflicts else ("requires_checking" if checks else "confirmed")
    checked["checks"] = list(dict.fromkeys(checks))
    return checked


def _ics_escape(value: Any) -> str:
    text = str(value or "")
    return (
        text.replace("\\", "\\\\")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def plan_to_ics(plan: dict[str, Any]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Unstuck City Compass//Plan a day//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-TIMEZONE:Europe/Warsaw",
    ]
    plan_id = str(plan.get("id") or "plan")
    for item in plan.get("items", []):
        start = datetime.fromisoformat(str(item["start"]))
        end = datetime.fromisoformat(str(item["end"]))
        source_end_unknown = item.get("kind") == "event" and item.get("source_event_end_status") == "unknown"
        uid = f"{plan_id.replace(':','-')}-{str(item['activity_id']).replace(':','-')}@unstuck-city-compass"
        notes = [
            item.get("description") or "",
            f"Source: {(item.get('source') or {}).get('url') or item.get('info_url') or 'not supplied'}",
            f"Availability: {item.get('availability') or 'unknown'}",
        ]
        price = item.get("price") or {}
        if price.get("min") is None or price.get("max") is None:
            notes.append("Price: unknown")
        else:
            notes.append(f"Price for plan party: {price['min']:.0f}-{price['max']:.0f} {price.get('currency','PLN')}")
        if source_end_unknown:
            notes.append("Actual event end time is unknown. No DTEND is exported for this event.")
        notes.extend(item.get("checks") or [])
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{_ics_escape(uid)}",
                f"DTSTAMP:{stamp}",
                f"DTSTART;TZID=Europe/Warsaw:{start.strftime('%Y%m%dT%H%M%S')}",
                *([] if source_end_unknown else [f"DTEND;TZID=Europe/Warsaw:{end.strftime('%Y%m%dT%H%M%S')}"]),
                f"SUMMARY:{_ics_escape(item['title'])}",
                f"LOCATION:{_ics_escape((item.get('venue') or {}).get('address') or (item.get('venue') or {}).get('name'))}",
                f"DESCRIPTION:{_ics_escape(chr(10).join(notes))}",
                f"URL:{_ics_escape(item.get('info_url') or '')}",
                "STATUS:TENTATIVE" if item.get("checks") else "STATUS:CONFIRMED",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
