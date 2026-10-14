"""One-off bounded live coverage probe for exact, already-curated Warsaw venues.

This script is intentionally not part of normal smoke coverage. It sends two
planner requests whose ten restaurant candidates are pinned explicitly, so the
existing planner/Qloo path reports which exact venue IDs resolve. It does not
search or enumerate arbitrary Qloo entities and does not persist results.
"""
from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

BASE = os.environ.get("UNSTUCK_PUBLIC_URL", "https://unstuck-city-compass.onrender.com").rstrip("/")

GROUPS = [
    [
        "warsaw:osm:way:1005658204",
        "warsaw:osm:node:2025189688",
        "warsaw:osm:node:316886479",
        "warsaw:osm:node:2859884304",
        "warsaw:osm:node:334008611",
        "warsaw:osm:node:4730432126",
        "warsaw:osm:way:400071446",
        "warsaw:osm:node:338486362",
        "warsaw:osm:node:447986173",
        "warsaw:osm:node:6023094185",
    ],
    [
        "warsaw:osm:node:2640176381",
        "warsaw:osm:node:416560107",
        "warsaw:osm:node:4741653125",
        "warsaw:osm:node:7705273908",
        "warsaw:osm:node:5073937636",
        "warsaw:osm:node:4834770520",
        "warsaw:osm:node:1285589018",
        "warsaw:osm:node:5062561421",
        "warsaw:osm:node:9773126020",
        "warsaw:osm:node:3582751797",
    ],
]


def post_json(path: str, payload: dict) -> dict:
    request = Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Unstuck-coverage-probe/1"},
        method="POST",
    )
    with urlopen(request, timeout=45) as response:
        return json.load(response)


def probe(place_ids: list[str]) -> dict:
    brief = {
        "date": "2026-10-17",
        "start_time": "10:00",
        "end_time": "22:30",
        "origin": "Warsaw Central",
        "return_required": True,
        "return_origin": "Warsaw Central",
        "people": 2,
        "budget_total": 2000,
        "activity_count": 1,
        "pace": "balanced",
        "travel_mode": "transit",
        "event_buffer_minutes": 15,
        "include_meal": True,
        "categories": [],
        "interests": [],
        "taste_refs": ["artist: Radiohead"],
        "must_include_ids": [f"restaurant:{place_id}" for place_id in place_ids],
        "locked_ids": [],
        "excluded_ids": [],
    }
    result = post_json("/api/planner/generate", brief)
    audit = result.get("taste_audit") or {}
    if audit.get("status") == "unavailable":
        raise RuntimeError(f"Qloo coverage probe unavailable: {audit.get('error_code')}")
    attempted = int(audit.get("candidate_count", 0))
    if attempted != len(place_ids):
        raise RuntimeError(f"Expected {len(place_ids)} pinned candidates, planner attempted {attempted}")
    return {
        "attempted_place_ids": place_ids,
        "status": audit.get("status"),
        "resolved_count": audit.get("resolved_count", 0),
        "ranked_count": audit.get("ranked_count", 0),
        "resolved_candidates": audit.get("resolved_candidates", []),
        "unresolved_candidate_ids": audit.get("unresolved_candidate_ids", []),
        "recognized_signals": audit.get("recognized_signals", []),
    }


def main() -> None:
    reports = []
    for index, group in enumerate(GROUPS, start=1):
        report = probe(group)
        reports.append(report)
        print(json.dumps({"qloo_coverage_group": index, **report}, ensure_ascii=False))
    print(json.dumps({
        "qloo_coverage_summary": {
            "attempted": sum(len(row["attempted_place_ids"]) for row in reports),
            "resolved": sum(int(row["resolved_count"]) for row in reports),
            "resolved_candidates": [
                candidate for row in reports for candidate in row["resolved_candidates"]
            ],
        }
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
