"""One-off production probe for the optional Qloo Good for both policy.

Run only with explicit [pair-smoke] commit opt-in; do not add to every deploy.
The public server holds the API key. This script never needs or logs it.
"""
from __future__ import annotations

import json

from production_smoke import get_json, post_json


def main() -> int:
    health = get_json("/api/health")
    if not health.get("ok") or health.get("provider_mode") != "live":
        raise RuntimeError("Pair smoke requires a healthy live Qloo public deployment")
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
        "taste_refs": ["artist: Radiohead"],
        "second_taste_refs": ["artist: Coldplay"],
        "meal_required": True,
        "negotiable_extra_travel_minutes": 0,
        "negotiable_stay_reduction_minutes": 30,
        "allow_category_change": False,
    }
    result = post_json("/api/search", demo)
    if result.get("provider_mode") != "live" or not result.get("cards"):
        raise RuntimeError("Paired search lost operational recommendations")
    if result["brief"].get("second_taste_refs") != demo["second_taste_refs"]:
        raise RuntimeError("Second taste profile was dropped from the public API")
    audit = result.get("taste_audit") or {}
    pair_status = audit.get("pair_status")
    if pair_status not in {"verified", "insufficient_coverage", "unavailable"}:
        raise RuntimeError(f"Unrecognized two-profile audit: {pair_status!r}")
    if pair_status == "unavailable":
        raise RuntimeError(
            f"Two-profile live Qloo unavailable (error={audit.get('error_code')!r}); "
            "quota or connection needs recheck"
        )
    if pair_status == "verified":
        positions = audit.get("pair_positions") or []
        if (audit.get("status") != "live" or len(positions) < 2
                or audit.get("profile_a_ranked_count", 0) < 2
                or audit.get("profile_b_ranked_count", 0) < 2
                or not audit.get("insights_called")):
            raise RuntimeError("Verified joint-Qloo ranking has inadequate evidence")
        if any(not (p.get("person_a_rank") and p.get("person_b_rank"))
               for p in positions):
            raise RuntimeError("One partner's Qloo rank was silently dropped")
    elif audit.get("status") != "no_coverage" or audit.get("ranked_order"):
        raise RuntimeError("Incomplete joint coverage must NOT claim a fair recommendation")
    print(json.dumps({
        "public_pair_smoke": "pass",
        "pair_status": pair_status,
        "pair_common_ranked_count": audit.get("ranked_entity_count", 0),
        "person_a_ranked_count": audit.get("profile_a_ranked_count", 0),
        "person_b_ranked_count": audit.get("profile_b_ranked_count", 0),
        "insights_called": audit.get("insights_called", False),
        "operational_cards_present": bool(result.get("cards")),
        "fairness_claimed": pair_status == "verified",
        "note": "A fallback is not a proven taste compromise; venue prices and openings still need verification.",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
