from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE = os.environ.get("UNSTUCK_PUBLIC_URL", "https://unstuck-city-compass.onrender.com").rstrip("/")


def get_json(path: str) -> dict:
    with urlopen(BASE + path, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(path: str, payload: dict) -> dict:
    request = Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # The application's JSON error is safe to show and explains failed live resolutions.
        detail = exc.read(1500).decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {path} returned HTTP {exc.code}: {detail}") from None


def post_raw(path: str, payload: dict) -> tuple[str, bytes]:
    request = Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=45) as response:
        return response.headers.get("Content-Type", ""), response.read()


def main() -> int:
    health = get_json("/api/health")
    if not health.get("ok"):
        raise RuntimeError("public health check failed")
    if health.get("google_places_enabled"):
        raise RuntimeError("Google Places must stay disabled during this development smoke")
    if health.get("provider_mode") != "live":
        raise RuntimeError(f"Production must run live Qloo; got {health.get('provider_mode')!r}")
    if not health.get("qloo_api_key_present"):
        raise RuntimeError("Production Qloo API credential is missing")

    demo = {
        "original_plan": "Dinner at HOŻA Steakhouse",
        "failed_place": "HOŻA Steakhouse",
        "failure_reason": "unavailable",
        "goal": "meal",
        "city": "Warsaw",
        "date": "2026-10-09",
        "start_time": "18:30",
        "return_by": "20:45",
        "min_stay_minutes": 120,
        "people": 2,
        "budget_total": 200,
        "currency": "PLN",
        "origin": "Warszawa Centralna",
        "travel_mode": "transit",
        "max_one_way_minutes": 25,
        "categories": ["restaurant"],
        "taste_refs": ["film: Amelie", "artist: Radiohead"],
        "meal_required": True,
        "negotiable_extra_travel_minutes": 0,
        "negotiable_stay_reduction_minutes": 30,
        "allow_category_change": False,
    }
    first = post_json("/api/search", demo)
    if not first.get("cards"):
        raise RuntimeError("60-second rescue scenario returned no cards")
    if first.get("strategy_used") != "shorter_stay":
        raise RuntimeError(f"demo did not use the intended minimal stay compromise: {first.get('strategy_used')}")
    if any(card.get("name") == "HOŻA Steakhouse" for card in first["cards"]):
        raise RuntimeError("failed venue reappeared in recommendations")
    if first.get("provider_mode") != "live" or first.get("taste_audit", {}).get("status") != "live":
        raise RuntimeError("Live Qloo search did not complete successfully")
    if not first.get("taste_audit", {}).get("recognized_signals"):
        raise RuntimeError("Live Qloo did not resolve any taste references")
    if first.get("taste_audit", {}).get("candidate_entity_count", 0) < 1:
        raise RuntimeError("Live Qloo did not resolve any candidate place for comparison")

    session_id = first["session_id"]
    rejected = first["cards"][0]["id"]
    second = post_json(
        "/api/reject",
        {"session_id": session_id, "place_id": rejected, "reason": "not_my_vibe"},
    )
    if rejected in {card["id"] for card in second.get("cards", [])}:
        raise RuntimeError("rejected venue returned immediately")
    if second.get("rejection_history", [])[-1].get("reason") != "not_my_vibe":
        raise RuntimeError("rejection reason was not preserved")

    restored = post_json("/api/undo-reject", {"session_id": session_id})
    if restored.get("restored_rejection", {}).get("place_id") != rejected:
        raise RuntimeError("undo did not restore the rejected venue")

    locked = post_json(
        "/api/update",
        {"session_id": session_id, "patch": {"negotiable_stay_reduction_minutes": 0}},
    )
    if locked.get("cards"):
        raise RuntimeError("locking the demo's required stay compromise should leave no feasible rescue")

    planner_catalog = get_json("/api/planner/catalog?date=2026-10-17")
    planner_ids = {row.get("id") for row in planner_catalog.get("items", [])}
    if "event:simple-plan-2026-10-17" not in planner_ids:
        raise RuntimeError("planner catalog is missing the fixed demo concert")

    planner_brief = {
        "date": "2026-10-17",
        "start_time": "10:00",
        "end_time": "22:30",
        "origin": "Warsaw Central",
        "return_required": True,
        "return_origin": "Warsaw Central",
        "people": 2,
        "budget_total": 500,
        "activity_count": 3,
        "pace": "balanced",
        "travel_mode": "transit",
        "event_buffer_minutes": 15,
        "include_meal": True,
        "categories": [],
        "interests": ["art", "rock"],
        "taste_refs": ["artist: Radiohead"],
        "must_include_ids": ["event:simple-plan-2026-10-17"],
        "locked_ids": ["event:simple-plan-2026-10-17"],
        "excluded_ids": [],
    }
    planner_result = post_json("/api/planner/generate", planner_brief)
    if not planner_result.get("plans"):
        raise RuntimeError("public Plan a day demo returned no plan")
    planner_plan = planner_result["plans"][0]
    planner_item_ids = {row["activity_id"] for row in planner_plan["items"]}
    if "event:simple-plan-2026-10-17" not in planner_item_ids:
        raise RuntimeError("planner lost the locked fixed event")
    if planner_result.get("taste_status") not in {"live_restaurants", "insufficient_coverage", "unavailable"}:
        raise RuntimeError("live planner must report actual Qloo restaurant coverage or a truthful fallback")
    if planner_result.get("taste_status") == "live_restaurants":
        evidence = planner_result.get("taste_audit") or {}
        if not evidence.get("insights_called") or evidence.get("ranked_count", 0) < 2:
            raise RuntimeError("planner claimed live Qloo without ranking at least two restaurants")
        comparison = evidence.get("same_pool_comparison") or {}
        if comparison.get("method") != "same_feasible_plan_pool":
            raise RuntimeError("planner did not expose a same-candidate-pool no-taste baseline")
        if comparison.get("with_qloo_top_plan_id") != planner_result["plans"][0]["id"]:
            raise RuntimeError("planner same-pool evidence does not match its own top recommendation")

    removable = next(
        row["activity_id"]
        for row in planner_plan["items"]
        if row["activity_id"] != "event:simple-plan-2026-10-17"
    )
    repaired = post_json(
        "/api/planner/repair",
        {"brief": planner_brief, "plan": planner_plan, "removed_id": removable},
    )
    if not repaired.get("plans"):
        raise RuntimeError("planner repair returned no alternative")
    repaired_ids = {row["activity_id"] for row in repaired["plans"][0]["items"]}
    if "event:simple-plan-2026-10-17" not in repaired_ids or removable in repaired_ids:
        raise RuntimeError("planner repair did not preserve the lock/exclusion")

    content_type, ics_body = post_raw("/api/planner/ics", {"plan": planner_plan})
    if "text/calendar" not in content_type or b"BEGIN:VCALENDAR" not in ics_body:
        raise RuntimeError("planner ICS export failed")

    # Regression for the upcoming judge window: a dated official event after
    # the original Oct 17 demo must be present and actually schedulable.
    recital_id = "event:fryderyk-chopin-recital-2026-11-08"
    future_catalog = get_json("/api/planner/catalog?date=2026-11-08")
    recital_listing = next((row for row in future_catalog.get("items", [])
                            if row.get("id") == recital_id), None)
    if not recital_listing or not recital_listing.get("schedulable"):
        raise RuntimeError("future official event was missing or not schedulable in public catalog")
    if recital_listing.get("availability") != "unknown" or recital_listing.get("price", {}).get("status") != "unknown":
        raise RuntimeError("event ticket inventory or price was presented as verified")
    future_brief = {
        **planner_brief,
        "date": "2026-11-08",
        "start_time": "13:00",
        "end_time": "21:30",
        "activity_count": 1,
        "include_meal": False,
        "interests": [],
        "taste_refs": [],  # No extra live Qloo quota for checking calendar integrity.
        "must_include_ids": [recital_id],
        "locked_ids": [recital_id],
    }
    future_plan = post_json("/api/planner/generate", future_brief)
    if not future_plan.get("plans") or not any(
        item.get("activity_id") == recital_id
        for item in future_plan["plans"][0].get("items", [])
    ):
        raise RuntimeError("dated official recital did not survive future-day planning")

    print(
        json.dumps(
            {
                "ok": True,
                "public_url": BASE,
                "demo_strategy": first.get("strategy_used"),
                "initial_cards": [card["name"] for card in first["cards"]],
                "reject_undo": True,
                "lock_compromise_result": locked.get("result_status"),
                "qloo_status": first.get("taste_audit", {}).get("status"),
                "planner_stops": len(planner_plan["items"]),
                "planner_repair": True,
                "planner_ics": True,
                "future_official_recital_scheduled": True,
                "planner_same_pool_changed_top": ((planner_result.get("taste_audit") or {}).get("same_pool_comparison") or {}).get("top_plan_changed"),
                "planner_taste_status": planner_result.get("taste_status"),
                "planner_qloo_coverage": {
                    "attempted": (planner_result.get("taste_audit") or {}).get("candidate_count"),
                    "resolved": (planner_result.get("taste_audit") or {}).get("resolved_count"),
                    "ranked": (planner_result.get("taste_audit") or {}).get("ranked_count"),
                    "insights_called": (planner_result.get("taste_audit") or {}).get("insights_called"),
                    "unresolved_candidate_count": len((planner_result.get("taste_audit") or {}).get("unresolved_candidate_ids", [])),
                    "recognized_interest_count": len((planner_result.get("taste_audit") or {}).get("recognized_signals", [])),
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
