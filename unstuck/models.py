from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any


ALLOWED_GOALS = {"meal", "coffee", "culture", "flexible"}
ALLOWED_MODES = {"walk", "transit"}


def _as_int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _time_string(value: Any, *, name: str) -> str:
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError(f"{name} must use HH:MM")
    try:
        hour, minute = map(int, parts)
    except ValueError as exc:
        raise ValueError(f"{name} must use HH:MM") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"{name} must use a valid 24-hour time")
    return f"{hour:02d}:{minute:02d}"


@dataclass(frozen=True)
class SearchBrief:
    original_plan: str
    failed_place: str
    failure_reason: str
    goal: str
    city: str
    date: str
    start_time: str
    return_by: str
    min_stay_minutes: int
    people: int
    budget_total: float
    currency: str
    origin: str
    travel_mode: str
    max_one_way_minutes: int
    categories: tuple[str, ...]
    taste_refs: tuple[str, ...]
    meal_required: bool
    negotiable_extra_travel_minutes: int = 0
    negotiable_stay_reduction_minutes: int = 0
    allow_category_change: bool = False
    origin_lat: float | None = None
    origin_lon: float | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SearchBrief":
        goal = str(payload.get("goal", "flexible")).strip().lower()
        if goal not in ALLOWED_GOALS:
            raise ValueError(f"goal must be one of: {', '.join(sorted(ALLOWED_GOALS))}")
        travel_mode = str(payload.get("travel_mode", "transit")).strip().lower()
        if travel_mode not in ALLOWED_MODES:
            raise ValueError("travel_mode must be walk or transit")
        date_text = str(payload.get("date", "")).strip()
        try:
            date.fromisoformat(date_text)
        except ValueError as exc:
            raise ValueError("date must use YYYY-MM-DD") from exc

        categories = tuple(
            dict.fromkeys(
                x.strip().lower()
                for x in payload.get("categories", [])
                if isinstance(x, str) and x.strip()
            )
        )
        taste_refs = tuple(
            dict.fromkeys(
                x.strip()
                for x in payload.get("taste_refs", [])
                if isinstance(x, str) and x.strip()
            )
        )
        try:
            budget = float(payload.get("budget_total", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("budget_total must be numeric") from exc
        if budget <= 0 or budget > 100000:
            raise ValueError("budget_total must be greater than 0")

        def optional_coord(name: str, minimum: float, maximum: float) -> float | None:
            raw = payload.get(name)
            if raw in (None, ""):
                return None
            try:
                value = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be numeric") from exc
            if not minimum <= value <= maximum:
                raise ValueError(f"{name} is outside the Warsaw pilot area")
            return value

        origin_lat = optional_coord("origin_lat", 52.05, 52.40)
        origin_lon = optional_coord("origin_lon", 20.75, 21.35)
        if (origin_lat is None) != (origin_lon is None):
            raise ValueError("origin_lat and origin_lon must be provided together")

        return cls(
            original_plan=str(payload.get("original_plan", "")).strip(),
            failed_place=str(payload.get("failed_place", "")).strip(),
            failure_reason=str(payload.get("failure_reason", "")).strip(),
            goal=goal,
            city=str(payload.get("city", "Warsaw")).strip() or "Warsaw",
            date=date_text,
            start_time=_time_string(payload.get("start_time"), name="start_time"),
            return_by=_time_string(payload.get("return_by"), name="return_by"),
            min_stay_minutes=_as_int(
                payload.get("min_stay_minutes", 60), name="min_stay_minutes", minimum=15, maximum=480
            ),
            people=_as_int(payload.get("people", 2), name="people", minimum=1, maximum=12),
            budget_total=budget,
            currency=str(payload.get("currency", "PLN")).strip().upper() or "PLN",
            origin=str(payload.get("origin", "Warsaw Central")).strip() or "Warsaw Central",
            travel_mode=travel_mode,
            max_one_way_minutes=_as_int(
                payload.get("max_one_way_minutes", 25), name="max_one_way_minutes", minimum=5, maximum=150
            ),
            categories=categories,
            taste_refs=taste_refs,
            meal_required=bool(payload.get("meal_required", goal == "meal")),
            negotiable_extra_travel_minutes=_as_int(
                payload.get("negotiable_extra_travel_minutes", 0),
                name="negotiable_extra_travel_minutes",
                minimum=0,
                maximum=60,
            ),
            negotiable_stay_reduction_minutes=_as_int(
                payload.get("negotiable_stay_reduction_minutes", 0),
                name="negotiable_stay_reduction_minutes",
                minimum=0,
                maximum=120,
            ),
            allow_category_change=bool(payload.get("allow_category_change", False)),
            origin_lat=origin_lat,
            origin_lon=origin_lon,
        )

    def patched(self, patch: dict[str, Any]) -> "SearchBrief":
        merged = self.to_dict()
        merged.update(patch)
        return SearchBrief.from_payload(merged)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_plan": self.original_plan,
            "failed_place": self.failed_place,
            "failure_reason": self.failure_reason,
            "goal": self.goal,
            "city": self.city,
            "date": self.date,
            "start_time": self.start_time,
            "return_by": self.return_by,
            "min_stay_minutes": self.min_stay_minutes,
            "people": self.people,
            "budget_total": self.budget_total,
            "currency": self.currency,
            "origin": self.origin,
            "travel_mode": self.travel_mode,
            "max_one_way_minutes": self.max_one_way_minutes,
            "categories": list(self.categories),
            "taste_refs": list(self.taste_refs),
            "meal_required": self.meal_required,
            "negotiable_extra_travel_minutes": self.negotiable_extra_travel_minutes,
            "negotiable_stay_reduction_minutes": self.negotiable_stay_reduction_minutes,
            "allow_category_change": self.allow_category_change,
            "origin_lat": self.origin_lat,
            "origin_lon": self.origin_lon,
        }


@dataclass(frozen=True)
class FactRange:
    minimum: float | None
    maximum: float | None
    unit: str
    status: str
    source_url: str | None = None
    checked_at: str | None = None
    basis: str = ""


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    city: str
    category: str
    serves_meal: bool
    address: str
    lat: float
    lon: float
    location_source_url: str | None
    location_checked_at: str | None
    price: FactRange
    hours: dict[str, tuple[tuple[str, str], ...]]
    date_exceptions: dict[str, tuple[tuple[str, str], ...]]
    hours_status: str
    hours_source_url: str | None
    hours_checked_at: str | None
    ambience: tuple[str, ...] = ()
    taste_tags: tuple[str, ...] = ()
    qloo_entity_id: str | None = None
    google_place_id: str | None = None
    source_note: str = ""
    demo_fixture: bool = False

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "Place":
        price = row.get("price") or {}
        hours: dict[str, tuple[tuple[str, str], ...]] = {}
        for day, windows in (row.get("hours") or {}).items():
            parsed: list[tuple[str, str]] = []
            for window in windows or []:
                if isinstance(window, list) and len(window) == 2:
                    parsed.append((str(window[0]), str(window[1])))
            hours[str(day)] = tuple(parsed)
        return cls(
            id=str(row["id"]),
            name=str(row["name"]),
            city=str(row.get("city", "Warsaw")),
            category=str(row.get("category", "other")).lower(),
            serves_meal=bool(row.get("serves_meal", False)),
            address=str(row.get("address", "")),
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            location_source_url=row.get("location_source_url"),
            location_checked_at=row.get("location_checked_at"),
            price=FactRange(
                minimum=float(price["min"]) if price.get("min") is not None else None,
                maximum=float(price["max"]) if price.get("max") is not None else None,
                unit=str(price.get("currency", "PLN")),
                status=str(price.get("status", "unknown")),
                source_url=price.get("source_url"),
                checked_at=price.get("checked_at"),
                basis=str(price.get("basis", "")),
            ),
            hours=hours,
            date_exceptions={
                str(day): tuple((str(window[0]), str(window[1])) for window in (windows or []) if isinstance(window, list) and len(window) == 2)
                for day, windows in (row.get("date_exceptions") or {}).items()
            },
            hours_status=str(row.get("hours_status", "unknown")),
            hours_source_url=row.get("hours_source_url"),
            hours_checked_at=row.get("hours_checked_at"),
            ambience=tuple(str(x) for x in row.get("ambience", [])),
            taste_tags=tuple(str(x) for x in row.get("taste_tags", [])),
            qloo_entity_id=row.get("qloo_entity_id"),
            google_place_id=row.get("google_place_id"),
            source_note=str(row.get("source_note", "")),
            demo_fixture=bool(row.get("demo_fixture", False)),
        )


@dataclass
class SearchState:
    brief: SearchBrief
    rejected_ids: set[str] = field(default_factory=set)
    rejection_history: list[dict[str, str]] = field(default_factory=list)
    route_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    round_no: int = 1

    def reject(self, place_id: str, reason: str = "skip") -> None:
        clean_id = str(place_id).strip()
        if not clean_id:
            raise ValueError("place_id is required")
        clean_reason = str(reason or "skip").strip().lower()
        if clean_reason not in {"skip", "too_far", "not_my_vibe", "been_there"}:
            raise ValueError("reason must be skip, too_far, not_my_vibe, or been_there")
        if clean_id not in self.rejected_ids:
            self.rejected_ids.add(clean_id)
            self.rejection_history.append({"place_id": clean_id, "reason": clean_reason})
        self.round_no += 1

    def undo_reject(self, place_id: str | None = None) -> dict[str, str] | None:
        if not self.rejection_history:
            return None
        index = None
        if place_id:
            for candidate in range(len(self.rejection_history) - 1, -1, -1):
                if self.rejection_history[candidate]["place_id"] == place_id:
                    index = candidate
                    break
        else:
            index = len(self.rejection_history) - 1
        if index is None:
            return None
        restored = self.rejection_history.pop(index)
        self.rejected_ids.discard(restored["place_id"])
        self.round_no += 1
        return restored

    def set_route_override(self, place_id: str, payload: dict[str, Any]) -> None:
        self.route_overrides[str(place_id)] = dict(payload)

    def update_brief(self, patch: dict[str, Any]) -> None:
        self.brief = self.brief.patched(patch)
        # A changed brief can invalidate previously checked route times.
        self.route_overrides.clear()
        self.round_no += 1
