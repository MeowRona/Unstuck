from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import date, datetime

from app import build_engine
from unstuck.planner import (
    DAY_KEYS,
    DayPlanner,
    PlannerBrief,
    PlannerCatalog,
    _dt,
    plan_to_ics,
    route_check_plan,
)


def brief(**patch):
    payload = {
        "date": "2026-10-17",
        "start_time": "10:00",
        "end_time": "23:00",
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
        "taste_refs": ["Radiohead"],
        "must_include_ids": [],
        "locked_ids": [],
        "excluded_ids": [],
    }
    payload.update(patch)
    return PlannerBrief.from_payload(payload)


class PlannerCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = build_engine("fixture", "real")
        cls.catalog = PlannerCatalog(engine.places)

    def test_verified_snapshot_has_resolvable_core_venues(self):
        for venue_id in ("venue:polin", "venue:kopernik", "venue:msn", "venue:muzeum-warszawy"):
            venue = self.catalog.venues[venue_id]
            self.assertIsNotNone(venue.get("lat"), venue_id)
            self.assertIsNotNone(venue.get("lon"), venue_id)

    def test_multiday_series_keeps_distinct_occurrences(self):
        rows = [row for row in self.catalog.events if row.get("series_id") == "series:targi-rzeczy-wyjatkowych-2026"]
        self.assertEqual({row["date"] for row in rows}, {"2026-10-17", "2026-10-18"})
        self.assertEqual(len(rows), 2)

    def test_closed_museum_is_marked_closed_for_specific_date(self):
        rows = {row["id"]: row for row in self.catalog.activities_for_date(date(2026, 10, 15))}
        self.assertEqual(rows["attraction:msn"]["date_status"], "closed")

    def test_unscheduled_festival_remains_discoverable_but_not_schedulable(self):
        row = next(row for row in self.catalog.discovery_rows() if row["id"] == "event:bodymind-2026")
        self.assertFalse(row["schedulable"])
        self.assertIn("Session time", row["unschedulable_reason"])

    def test_event_coverage_distinguishes_not_loaded_dates(self):
        payload = self.catalog.public_catalog("2027-01-15")
        coverage = payload["coverage"]
        self.assertEqual(coverage["event_sources_loaded_through"], "2026-11-09")


class DayPlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = build_engine("fixture", "real")
        cls.catalog = PlannerCatalog(engine.places)
        cls.planner = DayPlanner(cls.catalog)

    def test_plan_uses_fixed_concert_time_without_inventing_end(self):
        result = self.planner.generate(
            brief(
                activity_count=2,
                include_meal=False,
                must_include_ids=["event:simple-plan-2026-10-17"],
            )
        )
        self.assertTrue(result["plans"])
        event = next(
            item for item in result["plans"][0]["items"]
            if item["activity_id"] == "event:simple-plan-2026-10-17"
        )
        self.assertEqual(event["display_start"], "18:00")
        self.assertEqual(event["source_event_end_status"], "unknown")
        self.assertIn("Actual event end time is unknown.", event["checks"])

    def test_fixed_event_buffer_is_a_real_constraint(self):
        row = next(
            x for x in self.catalog.activities_for_date(date(2026, 10, 17))
            if x["id"] == "event:simple-plan-2026-10-17"
        )
        too_late_for_buffer = _dt(date(2026, 10, 17), "17:50")
        self.assertIsNone(
            self.planner._slot(
                row,
                date(2026, 10, 17),
                too_late_for_buffer,
                "balanced",
                15,
            )
        )
        self.assertIsNotNone(
            self.planner._slot(
                row,
                date(2026, 10, 17),
                too_late_for_buffer,
                "balanced",
                0,
            )
        )

    def test_unknown_price_is_not_counted_as_zero(self):
        result = self.planner.generate(
            brief(
                activity_count=1,
                include_meal=False,
                must_include_ids=["event:simple-plan-2026-10-17"],
            )
        )
        plan = result["plans"][0]
        self.assertEqual(plan["unknown_cost_components"], 1)
        self.assertEqual(plan["feasibility"], "requires_checking")
        self.assertTrue(any("budget cannot be guaranteed" in row for row in plan["checks"]))

    def test_last_entry_blocks_a_too_late_polin_visit(self):
        row = next(x for x in self.catalog.activities_for_date(date(2026, 10, 17)) if x["id"] == "attraction:polin-core")
        arrival = _dt(date(2026, 10, 17), "16:30")
        self.assertIsNone(self.planner._slot(row, date(2026, 10, 17), arrival, "balanced"))

    def test_closed_museum_cannot_be_a_required_item(self):
        result = self.planner.generate(
            brief(
                date="2026-10-15",
                activity_count=1,
                include_meal=False,
                must_include_ids=["attraction:msn"],
            )
        )
        self.assertEqual(result["plans"], [])
        self.assertTrue(any("closed" in row.lower() for row in result["explanation"]))

    def test_planner_can_drop_one_activity_instead_of_breaking_time(self):
        result = self.planner.generate(
            brief(
                start_time="16:30",
                end_time="21:30",
                activity_count=4,
                include_meal=False,
                must_include_ids=["event:simple-plan-2026-10-17"],
            )
        )
        self.assertTrue(result["plans"])
        self.assertLessEqual(result["planned_activity_count"], 4)
        if result["planned_activity_count"] < 4:
            self.assertIn("Only", result["explanation"])

    def test_cancelled_and_sold_out_required_events_are_blockers(self):
        items = self.catalog.activities_for_date(date(2026, 10, 17))
        cancelled = deepcopy(next(x for x in items if x["id"] == "event:simple-plan-2026-10-17"))
        cancelled["id"] = "event:cancelled"
        cancelled["status"] = "cancelled"
        sold = deepcopy(cancelled)
        sold["id"] = "event:sold"
        sold["status"] = "planned"
        sold["availability"] = "sold_out"
        b = brief(must_include_ids=["event:cancelled", "event:sold"])
        eligible, blockers = self.planner._eligible(items + [cancelled, sold], b)
        self.assertNotIn("event:cancelled", {row["id"] for row in eligible})
        self.assertNotIn("event:sold", {row["id"] for row in eligible})
        self.assertTrue(any("cancelled" in row for row in blockers))
        self.assertTrue(any("sold out" in row for row in blockers))

    def test_route_check_departures_follow_previous_activity_end(self):
        result = self.planner.generate(
            brief(
                activity_count=2,
                include_meal=False,
                must_include_ids=["event:simple-plan-2026-10-17"],
            )
        )
        plan = result["plans"][0]
        departures = []

        def fake_route(_start, _end, depart_at, _mode):
            departures.append(depart_at)
            return {
                "duration_minutes": 12,
                "scheduled": True,
                "realtime": False,
                "source": {"name": "fixture route", "url": "https://example.test/route"},
                "legs": [],
            }

        checked = route_check_plan(plan, brief(activity_count=2, include_meal=False, must_include_ids=["event:simple-plan-2026-10-17"]), fake_route)
        self.assertEqual(checked["route_status"], "checked")
        self.assertGreaterEqual(len(departures), 2)
        for earlier, later in zip(departures, departures[1:]):
            self.assertGreater(later, earlier)

    def test_checked_route_can_push_flexible_attraction_past_last_entry(self):
        result = self.planner.generate(
            brief(
                date="2026-10-17",
                start_time="10:00",
                end_time="22:00",
                activity_count=1,
                include_meal=False,
                must_include_ids=["attraction:polin-core"],
            )
        )
        self.assertTrue(result["plans"])
        plan = result["plans"][0]

        def very_slow_route(_start, _end, _depart_at, _mode):
            return {
                "duration_minutes": 390,
                "scheduled": True,
                "realtime": False,
                "source": {"name": "fixture slow route"},
                "legs": [],
            }

        checked = route_check_plan(
            plan,
            brief(
                date="2026-10-17",
                start_time="10:00",
                end_time="22:00",
                activity_count=1,
                include_meal=False,
                must_include_ids=["attraction:polin-core"],
            ),
            very_slow_route,
        )
        self.assertEqual(checked["feasibility"], "conflict")
        self.assertTrue(
            any("last accepted entry" in row or "opening window" in row for row in checked["route_conflicts"])
        )

    def test_repair_keeps_locked_item_and_excludes_removed_item(self):
        b = brief(
            activity_count=3,
            include_meal=False,
            must_include_ids=["event:simple-plan-2026-10-17"],
            locked_ids=["event:simple-plan-2026-10-17"],
        )
        original = self.planner.generate(b)["plans"][0]
        removable = next(item["activity_id"] for item in original["items"] if item["activity_id"] != "event:simple-plan-2026-10-17")
        repaired = self.planner.repair(original, b, removable)
        self.assertTrue(repaired["plans"])
        new_ids = {item["activity_id"] for item in repaired["plans"][0]["items"]}
        self.assertIn("event:simple-plan-2026-10-17", new_ids)
        self.assertNotIn(removable, new_ids)
        self.assertIn("event:simple-plan-2026-10-17", repaired["plans"][0]["repair"]["locked_ids"])

    def test_midnight_window_and_warsaw_dst_are_timezone_aware(self):
        overnight = brief(date="2026-10-24", start_time="22:00", end_time="01:00", activity_count=1, include_meal=False)
        self.assertEqual(overnight.start_time, "22:00")
        before = _dt(date(2026, 10, 25), "02:30")
        after = _dt(date(2026, 10, 25), "03:30")
        self.assertNotEqual(before.utcoffset(), after.utcoffset())


class IcsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = build_engine("fixture", "real")
        catalog = PlannerCatalog(engine.places)
        cls.planner = DayPlanner(catalog)

    def test_ics_keeps_polish_text_stable_uid_and_unknown_event_end(self):
        result = self.planner.generate(
            brief(activity_count=1, include_meal=False, must_include_ids=["event:simple-plan-2026-10-17"])
        )
        plan = result["plans"][0]
        plan["items"][0]["title"] = "Koncert — Łódź / Żółć"
        ics = plan_to_ics(plan)
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("TZID=Europe/Warsaw", ics)
        self.assertIn("Koncert — Łódź / Żółć", ics)
        self.assertIn("@unstuck-city-compass", ics)
        self.assertNotIn("DTEND;TZID=Europe/Warsaw", ics)
        self.assertIn("Actual event end time is unknown", ics)


if __name__ == "__main__":
    unittest.main()
