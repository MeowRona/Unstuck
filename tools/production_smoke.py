from __future__ import annotations

import json
import os
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
    with urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    health = get_json("/api/health")
    if not health.get("ok"):
        raise RuntimeError("public health check failed")
    if health.get("google_places_enabled"):
        raise RuntimeError("Google Places must stay disabled during this development smoke")

    demo = {
        "original_plan": "Dinner at HOŻA Steakhouse",
        "failed_place": "HOŻA Steakhouse",
        "failure_reason": "unavailable",
        "goal": "meal",
        "city": "Warsaw",
        "date": "2026-10-09",
        "start_time": "18:30",
        "return_by": "20:25",
        "min_stay_minutes": 120,
        "people": 2,
        "budget_total": 200,
        "currency": "PLN",
        "origin": "Warszawa Centralna",
        "travel_mode": "transit",
        "max_one_way_minutes": 25,
        "categories": ["restaurant"],
        "taste_refs": ["Amelie", "Radiohead"],
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
    if first.get("taste_audit", {}).get("status") != "fixture_preview":
        raise RuntimeError("hosted beta must not claim live Qloo before the connection is enabled")

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
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
