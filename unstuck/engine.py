from __future__ import annotations

import math
from dataclasses import dataclass
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .models import Place, SearchBrief, SearchState
from .origins import resolve_origin
from .providers import TasteResult


def _last_sunday(year: int, month: int) -> date:
    last = date(year, month, monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - 6) % 7)


def _warsaw_timezone(local_naive: datetime) -> timezone:
    """Return CET/CEST using current EU transition rules, without external tzdata.

    Unstuck's first geographic scope is Warsaw. Transition-hour inputs are uncommon
    for the product, but the boundary is still handled explicitly enough to avoid
    silently treating all dates as a fixed offset.
    """
    spring = _last_sunday(local_naive.year, 3)
    autumn = _last_sunday(local_naive.year, 10)
    current = local_naive.date()
    if spring < current < autumn:
        return timezone(timedelta(hours=2), "CEST")
    if current < spring or current > autumn:
        return timezone(timedelta(hours=1), "CET")
    if current == spring:
        return timezone(timedelta(hours=2 if local_naive.hour >= 3 else 1), "CEST" if local_naive.hour >= 3 else "CET")
    # On the autumn transition day, 02:xx is ambiguous. We conservatively treat it
    # as the later standard-time occurrence; normal daytime/evening inputs are exact.
    return timezone(timedelta(hours=2 if local_naive.hour < 2 else 1), "CEST" if local_naive.hour < 2 else "CET")


@dataclass(frozen=True)
class Evaluation:
    place: Place
    affinity: float | None
    taste_rank: int | None
    taste_evidence: tuple[str, ...]
    taste_source: str
    travel_minutes: int
    stay_minutes: int
    arrival: datetime
    departure: datetime
    return_time: datetime
    estimated_total_min: float | None
    estimated_total_max: float | None
    hard_failures: tuple[str, ...]
    needs_checking: tuple[str, ...]
    changes: tuple[dict[str, Any], ...]
    preserved: tuple[str, ...]

    @property
    def viable(self) -> bool:
        return not self.hard_failures

    @property
    def confirmed(self) -> bool:
        return self.viable and not self.needs_checking


def _minutes(text: str) -> int:
    hour, minute = map(int, text.split(":"))
    return hour * 60 + minute


def _haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius = 6371.0
    p1 = math.radians(a_lat)
    p2 = math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(h))


def estimate_travel_minutes(brief: SearchBrief, place: Place) -> int:
    origin = (
        (brief.origin_lat, brief.origin_lon)
        if brief.origin_lat is not None and brief.origin_lon is not None
        else resolve_origin(brief.origin)
    )
    distance = _haversine_km(origin[0], origin[1], place.lat, place.lon)
    if brief.travel_mode == "walk":
        return max(4, int(math.ceil(distance / 4.6 * 60)))
    # Conservative city-centre transit estimate. This is explicitly shown as an estimate in the UI.
    return max(8, int(math.ceil(7 + distance * 3.0)))


def _local_datetimes(brief: SearchBrief) -> tuple[datetime, datetime]:
    start_naive = datetime.fromisoformat(f"{brief.date}T{brief.start_time}")
    return_naive = datetime.fromisoformat(f"{brief.date}T{brief.return_by}")
    start = start_naive.replace(tzinfo=_warsaw_timezone(start_naive))
    return_candidate = return_naive.replace(tzinfo=_warsaw_timezone(return_naive))
    if return_candidate <= start:
        next_day = return_naive + timedelta(days=1)
        return_candidate = next_day.replace(tzinfo=_warsaw_timezone(next_day))
    return start, return_candidate


def _window_contains(place: Place, start: datetime, end: datetime) -> bool | None:
    if place.hours_status in {"unknown", "unverified"} or not place.hours:
        if place.hours_status in {"unknown", "unverified"}:
            return None
        return False
    exception_key = start.date().isoformat()
    if exception_key in place.date_exceptions:
        windows = place.date_exceptions[exception_key]
        if not windows:
            return False
    else:
        day_key = str(start.weekday())
        windows = place.hours.get(day_key, ())
    if not windows:
        return False
    start_m = start.hour * 60 + start.minute
    end_m = end.hour * 60 + end.minute
    if end.date() > start.date():
        end_m += 1440
    for opens, closes in windows:
        open_m = _minutes(opens)
        close_m = _minutes(closes)
        if close_m <= open_m:
            close_m += 1440
        if open_m <= start_m and end_m <= close_m:
            return True
    return False


def evaluate_place(
    place: Place,
    brief: SearchBrief,
    taste: TasteResult | None,
    *,
    allowed_travel_minutes: int,
    stay_minutes: int,
    category_relaxed: bool,
) -> Evaluation:
    start, return_by = _local_datetimes(brief)
    travel = estimate_travel_minutes(brief, place)
    arrival = start + timedelta(minutes=travel)
    departure = arrival + timedelta(minutes=stay_minutes)
    return_time = departure + timedelta(minutes=travel)
    hard: list[str] = []
    needs: list[str] = []
    changes: list[dict[str, Any]] = []
    preserved: list[str] = []

    if brief.meal_required and not place.serves_meal:
        hard.append("Does not satisfy the required meal goal")
    else:
        preserved.append("Required goal")

    if brief.categories and place.category not in brief.categories:
        if category_relaxed and brief.allow_category_change:
            changes.append({"field": "category", "from": ", ".join(brief.categories), "to": place.category})
        else:
            hard.append("Outside the selected categories")
    else:
        preserved.append("Category")

    if travel > allowed_travel_minutes:
        hard.append(f"Estimated one-way travel is {travel} min, above the allowed {allowed_travel_minutes} min")
    elif travel > brief.max_one_way_minutes:
        changes.append(
            {
                "field": "one-way travel",
                "from": f"≤ {brief.max_one_way_minutes} min",
                "to": f"≈ {travel} min",
                "delta": travel - brief.max_one_way_minutes,
                "unit": "min",
            }
        )
    else:
        preserved.append("Travel limit")

    if stay_minutes < brief.min_stay_minutes:
        changes.append(
            {
                "field": "minimum stay",
                "from": f"{brief.min_stay_minutes} min",
                "to": f"{stay_minutes} min",
                "delta": brief.min_stay_minutes - stay_minutes,
                "unit": "min shorter",
            }
        )
    else:
        preserved.append("Minimum stay")

    if return_time > return_by:
        hard.append(
            f"Estimated return would be {return_time.strftime('%H:%M')}, after the locked {return_by.strftime('%H:%M')}"
        )
    else:
        preserved.append("Return time")

    cost_min = cost_max = None
    if place.price.minimum is not None and place.price.maximum is not None and place.price.unit == brief.currency:
        cost_min = place.price.minimum * brief.people
        cost_max = place.price.maximum * brief.people
        if cost_max > brief.budget_total:
            hard.append(
                f"Upper cost estimate is {cost_max:.0f} {brief.currency}, above the locked {brief.budget_total:.0f} {brief.currency} budget"
            )
        else:
            preserved.append("Budget")
        if place.price.status not in {"confirmed", "fixture"}:
            needs.append("Price range is not confirmed enough for a hard-budget guarantee")
    else:
        needs.append("Price is missing or uses a different currency; hard-budget fit is not confirmed")

    open_status = _window_contains(place, arrival, departure)
    if open_status is False:
        hard.append("Published hours do not cover the planned visit window")
    elif open_status is None:
        needs.append("Opening hours are not confirmed for this visit")
    else:
        if place.hours_status not in {"confirmed", "fixture"}:
            needs.append("Opening hours are estimated and need confirmation for this visit")
        else:
            preserved.append("Opening window")

    if place.price.status not in {"confirmed", "fixture"} and "Budget" in preserved:
        preserved.remove("Budget")

    return Evaluation(
        place=place,
        affinity=taste.affinity if taste else None,
        taste_rank=taste.rank if taste else None,
        taste_evidence=taste.evidence if taste else (),
        taste_source=taste.source if taste else "none",
        travel_minutes=travel,
        stay_minutes=stay_minutes,
        arrival=arrival,
        departure=departure,
        return_time=return_time,
        estimated_total_min=cost_min,
        estimated_total_max=cost_max,
        hard_failures=tuple(hard),
        needs_checking=tuple(needs),
        changes=tuple(changes),
        preserved=tuple(dict.fromkeys(preserved)),
    )


def _change_vector(ev: Evaluation) -> tuple[int, int, int]:
    travel_delta = sum(int(c.get("delta", 0)) for c in ev.changes if c.get("field") == "one-way travel")
    stay_delta = sum(int(c.get("delta", 0)) for c in ev.changes if c.get("field") == "minimum stay")
    category_change = 1 if any(c.get("field") == "category" for c in ev.changes) else 0
    return travel_delta, stay_delta, category_change


def _dominates(a: Evaluation, b: Evaluation) -> bool:
    av = _change_vector(a)
    bv = _change_vector(b)
    return all(x <= y for x, y in zip(av, bv)) and any(x < y for x, y in zip(av, bv))


def pareto_front(evaluations: list[Evaluation]) -> list[Evaluation]:
    # Many venues share the exact same compromise vector (especially in the
    # strict strategy where it is commonly (0, 0, 0)). Comparing every venue
    # against every other venue makes the cost quadratic in catalog size even
    # though dominance depends only on the three-value vector. Group by vector,
    # find the non-dominated vectors, then expand the surviving groups. This is
    # semantically identical to the brute-force definition while keeping a full
    # Warsaw restaurant catalog responsive.
    by_vector: dict[tuple[int, int, int], list[Evaluation]] = {}
    for ev in evaluations:
        by_vector.setdefault(_change_vector(ev), []).append(ev)
    vectors = list(by_vector)

    def vector_dominates(a: tuple[int, int, int], b: tuple[int, int, int]) -> bool:
        return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))

    surviving = {
        vector
        for vector in vectors
        if not any(vector_dominates(other, vector) for other in vectors if other != vector)
    }
    return [ev for vector in vectors if vector in surviving for ev in by_vector[vector]]


def _sort_key(ev: Evaluation) -> tuple[Any, ...]:
    vector = _change_vector(ev)
    unknown_penalty = len(ev.needs_checking)
    affinity_sort = -(ev.affinity if ev.affinity is not None else -1.0)
    taste_rank = ev.taste_rank if ev.taste_rank is not None else 9999
    return (sum(vector), vector, unknown_penalty, affinity_sort, taste_rank, ev.place.name.casefold())


def _card(ev: Evaluation, brief: SearchBrief) -> dict[str, Any]:
    price_source = {
        "status": ev.place.price.status,
        "url": ev.place.price.source_url,
        "checked_at": ev.place.price.checked_at,
    }
    hours_source = {
        "status": ev.place.hours_status,
        "url": ev.place.hours_source_url,
        "checked_at": ev.place.hours_checked_at,
    }
    if ev.affinity is None:
        fit = "No taste signal was available; feasibility drove this result."
    elif ev.taste_source == "fixture":
        refs = ", ".join(ev.taste_evidence) if ev.taste_evidence else "the selected references"
        fit = f"Fixture taste data ranks this option against {refs}. This is demo data, not a Qloo response."
    else:
        if ev.taste_evidence:
            refs = ", ".join(ev.taste_evidence)
            fit = f"Qloo ranked this place within the same candidate pool; returned explainability referenced {refs}."
        else:
            fit = "Qloo ranked this place within the same candidate pool for the selected taste references; no per-result explainability was returned."
    return {
        "id": ev.place.id,
        "name": ev.place.name,
        "category": ev.place.category,
        "address": ev.place.address,
        "location": {
            "lat": ev.place.lat,
            "lon": ev.place.lon,
        },
        "google_place_id": ev.place.google_place_id,
        "keep": list(ev.preserved),
        "change": list(ev.changes),
        "why_this_fits": fit,
        "needs_checking": list(ev.needs_checking),
        "taste": {
            "source": ev.taste_source,
            "affinity": ev.affinity,
            "rank": ev.taste_rank,
            "evidence": list(ev.taste_evidence),
        },
        "timing": {
            "travel_one_way_minutes": ev.travel_minutes,
            "travel_is_estimate": True,
            "arrival": ev.arrival.strftime("%H:%M"),
            "stay_minutes": ev.stay_minutes,
            "leave": ev.departure.strftime("%H:%M"),
            "estimated_return": ev.return_time.strftime("%H:%M"),
        },
        "cost": {
            "for_people": brief.people,
            "min": ev.estimated_total_min,
            "max": ev.estimated_total_max,
            "currency": brief.currency,
            "source": price_source,
            "basis": ev.place.price.basis,
        },
        "hours_source": hours_source,
        "location_source": {
            "url": ev.place.location_source_url,
            "checked_at": ev.place.location_checked_at,
        },
        "source_note": ev.place.source_note,
        "demo_fixture": ev.place.demo_fixture,
        "feasibility_status": "confirmed" if ev.confirmed else "requires_checking",
    }


class UnstuckEngine:
    def __init__(self, places: list[Place], taste_provider):
        self.places = places
        self.taste_provider = taste_provider

    def search(self, state: SearchState) -> dict[str, Any]:
        brief = state.brief
        excluded_names = {brief.failed_place.casefold()} if brief.failed_place else set()
        ranked_universe = [
            p
            for p in self.places
            if p.city.casefold() == brief.city.casefold()
            and p.name.casefold() not in excluded_names
        ]
        remaining_count = sum(1 for p in ranked_universe if p.id not in state.rejected_ids)
        log: list[str] = []
        log.append(f"Round {state.round_no}: {remaining_count} candidates remain after exclusions/rejections.")
        # Qloo should rank a relevant pool, not spend API calls resolving every restaurant in Warsaw.
        # This prefilter uses only hard feasibility / geography; taste is intentionally not considered here.
        allowed_travel = brief.max_one_way_minutes + brief.negotiable_extra_travel_minutes
        prefiltered: list[tuple[tuple[Any, ...], Place]] = []
        for place in ranked_universe:
            if brief.meal_required and not place.serves_meal:
                continue
            travel = estimate_travel_minutes(brief, place)
            if travel > allowed_travel:
                continue
            if (
                place.price.maximum is not None
                and place.price.unit == brief.currency
                and place.price.status in {"confirmed", "fixture"}
                and place.price.maximum * brief.people > brief.budget_total
            ):
                continue
            category_penalty = 0 if not brief.categories or place.category in brief.categories else 1
            fact_penalty = int(place.price.status not in {"confirmed", "fixture"}) + int(
                place.hours_status not in {"confirmed", "fixture"}
            )
            prefiltered.append(((category_penalty, fact_penalty, travel, place.name.casefold()), place))
        prefiltered.sort(key=lambda row: row[0])
        ordered_prefiltered = [place for _key, place in prefiltered]

        # Keep ranking stable across reject rounds. In fixture/baseline mode we can
        # rank the whole feasible universe cheaply. In live mode, Qloo's canonical
        # rank workflow accepts up to 10 options, so keep a stable 10-place window
        # until it is almost exhausted, then advance to the next layer. This means
        # one rejection does not trigger a totally new taste universe or burn a new
        # Qloo request unnecessarily.
        if self.taste_provider.mode == "live":
            head = ordered_prefiltered[:10]
            head_remaining = [p for p in head if p.id not in state.rejected_ids]
            if len(head_remaining) >= 3 or len(ordered_prefiltered) <= 10:
                rank_pool = head
            else:
                carry = head_remaining
                tail = [p for p in ordered_prefiltered[10:] if p.id not in state.rejected_ids]
                rank_pool = carry + tail[: max(0, 10 - len(carry))]
            log.append(
                f"Live Qloo ranking window contains {len(rank_pool)} option(s); rejected options stay in-window until the tier is nearly exhausted."
            )
        else:
            rank_pool = ordered_prefiltered
            log.append(f"Taste-ranking pool contains {len(rank_pool)} candidates after hard prefiltering.")

        taste_results = self.taste_provider.rank(rank_pool, brief.taste_refs)
        taste_by_place = {row.place_id: row for row in taste_results}
        log.append(f"Taste provider '{self.taste_provider.mode}' ranked the current candidate pool.")

        candidates = [place for place in rank_pool if place.id not in state.rejected_ids]

        strategies: list[tuple[str, int, int, bool]] = [
            ("strict", brief.max_one_way_minutes, brief.min_stay_minutes, False)
        ]
        if brief.negotiable_extra_travel_minutes:
            strategies.append(
                (
                    "expand_travel",
                    brief.max_one_way_minutes + brief.negotiable_extra_travel_minutes,
                    brief.min_stay_minutes,
                    False,
                )
            )
        if brief.negotiable_stay_reduction_minutes:
            strategies.append(
                (
                    "shorter_stay",
                    brief.max_one_way_minutes + brief.negotiable_extra_travel_minutes,
                    max(15, brief.min_stay_minutes - brief.negotiable_stay_reduction_minutes),
                    False,
                )
            )
        if brief.allow_category_change:
            strategies.append(
                (
                    "category_change",
                    brief.max_one_way_minutes + brief.negotiable_extra_travel_minutes,
                    max(15, brief.min_stay_minutes - brief.negotiable_stay_reduction_minutes),
                    True,
                )
            )

        viable: list[Evaluation] = []
        provisional: list[Evaluation] = []
        same_strategy_provisional: list[Evaluation] = []
        strategy_used = "strict"
        last_evaluated: list[Evaluation] = []
        for strategy_name, travel_limit, stay_minutes, category_relaxed in strategies:
            evaluated = [
                evaluate_place(
                    place,
                    brief,
                    taste_by_place.get(place.id),
                    allowed_travel_minutes=travel_limit,
                    stay_minutes=stay_minutes,
                    category_relaxed=category_relaxed,
                )
                for place in candidates
            ]
            last_evaluated = evaluated
            current = [ev for ev in evaluated if ev.confirmed]
            current_provisional = [ev for ev in evaluated if ev.viable and not ev.confirmed]
            log.append(
                f"Strategy '{strategy_name}' found {len(current)} confirmed and {len(current_provisional)} provisional candidate(s)."
            )
            if current:
                viable = current
                same_strategy_provisional = current_provisional
                strategy_used = strategy_name
                break
            if current_provisional and not provisional:
                provisional = current_provisional
                strategy_used = strategy_name
            if strategy_name != strategies[-1][0]:
                log.append("No feasible option yet; trying the next explicitly allowed compromise.")

        chosen_pool = viable if viable else provisional
        front = pareto_front(chosen_pool)
        front.sort(key=_sort_key)
        selected = front[:3]
        if viable and same_strategy_provisional:
            provisional_front = pareto_front(same_strategy_provisional)
            # A provisional slot is useful when it expands real choice, but it must remain
            # visibly provisional. For this slot, taste/travel are more useful than simply
            # preferring the same few fully-sourced seed venues every time.
            provisional_front.sort(
                key=lambda ev: (
                    ev.travel_minutes,
                    -(ev.affinity if ev.affinity is not None else -1.0),
                    len(ev.needs_checking),
                    ev.place.name.casefold(),
                )
            )
            if len(selected) < 3:
                needed = 3 - len(selected)
                additions = provisional_front[:needed]
                selected.extend(additions)
                if additions:
                    log.append(
                        f"Filled {len(additions)} remaining result slot(s) with clearly marked provisional alternatives to preserve useful choice."
                    )
            exploratory = provisional_front[0] if provisional_front else None
            if len(selected) >= 3 and exploratory is not None and exploratory not in selected:
                confirmed_affinities = [ev.affinity for ev in selected if ev.affinity is not None]
                best_affinity = max(confirmed_affinities) if confirmed_affinities else None
                improves_taste = (
                    exploratory.affinity is not None
                    and best_affinity is not None
                    and exploratory.affinity >= best_affinity
                )
                improves_travel = exploratory.travel_minutes + 5 <= max(ev.travel_minutes for ev in selected)
                if improves_taste or improves_travel:
                    selected = selected[:2] + [exploratory]
                    log.append(
                        "Included one clearly marked provisional alternative because it materially improves taste or travel."
                    )
        if selected:
            if viable:
                confirmed_count = sum(1 for ev in selected if ev.confirmed)
                provisional_count = len(selected) - confirmed_count
                if provisional_count:
                    log.append(
                        f"Removed dominated alternatives and kept {confirmed_count} confirmed + "
                        f"{provisional_count} clearly marked provisional option(s)."
                    )
                else:
                    log.append(f"Removed dominated alternatives and kept {confirmed_count} confirmed non-dominated option(s).")
            else:
                log.append(
                    f"No option could be confirmed from available facts; showing {len(selected)} non-dominated option(s) that require checking."
                )
        else:
            log.append("Search stopped: no feasible option exists inside the checked pool and allowed compromises.")

        blockers: dict[str, int] = {}
        for ev in last_evaluated:
            for failure in ev.hard_failures:
                blockers[failure] = blockers.get(failure, 0) + 1

        return {
            "round": state.round_no,
            "brief": brief.to_dict(),
            "rejected_ids": sorted(state.rejected_ids),
            "provider_mode": self.taste_provider.mode,
            "strategy_used": strategy_used,
            "cards": [_card(ev, brief) for ev in selected],
            "empty": not bool(selected),
            "result_status": "confirmed" if viable else ("requires_checking" if selected else "no_result"),
            "empty_explanation": [
                {"reason": reason, "count": count}
                for reason, count in sorted(blockers.items(), key=lambda x: (-x[1], x[0]))[:5]
            ] if not selected else [],
            "agent_log": log,
            "scope": {
                "city": brief.city,
                "candidate_count": len(candidates),
                "rank_pool_count": len(rank_pool),
                "catalog_size": len(self.places),
                "travel_note": "Travel is a straight-line-derived city estimate, not a live route guarantee.",
            },
        }
