from __future__ import annotations

import os
import sys
from pathlib import Path

from app import build_engine
from unstuck.models import SearchBrief, SearchState


def main() -> int:
    if not os.environ.get("QLOO_API_KEY"):
        print("BLOCKED_NO_API_KEY: QLOO_API_KEY is not set. No live Qloo request was attempted.")
        return 2
    real_catalog = Path(__file__).resolve().parent / "data" / "places_warsaw.json"
    if not real_catalog.exists():
        print("BLOCKED_NO_REAL_CATALOG: data/places_warsaw.json is missing.")
        return 2

    payload = {
        "original_plan": "Dinner in central Warsaw",
        "failed_place": "",
        "failure_reason": "",
        "goal": "meal",
        "city": "Warsaw",
        "date": "2026-10-10",
        "start_time": "18:30",
        "return_by": "22:30",
        "min_stay_minutes": 60,
        "people": 2,
        "budget_total": 200,
        "currency": "PLN",
        "origin": "Warsaw Central",
        "travel_mode": "transit",
        "max_one_way_minutes": 30,
        "categories": ["restaurant"],
        "taste_refs": ["Blade Runner", "Radiohead"],
        "meal_required": True,
        "negotiable_extra_travel_minutes": 0,
        "negotiable_stay_reduction_minutes": 0,
        "allow_category_change": False,
    }
    try:
        result = build_engine("live", "real").search(SearchState(SearchBrief.from_payload(payload)))
    except (RuntimeError, ValueError) as exc:
        print(f"FAIL_LIVE_QLOO: {exc}")
        return 1
    print(f"PASS_LIVE_QLOO: provider={result['provider_mode']} cards={len(result['cards'])} status={result['result_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
