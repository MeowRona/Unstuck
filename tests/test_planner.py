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

    def test_restaurant_pool_expands_with_explicit_unknown_fact_status(self):
        rows = self.catalog.restaurant_rows
        self.assertGreaterEqual(len(rows), 10)
        self.assertLessEqual(len(rows), 32)
        self.assertEqual(len({row["id"] for row in rows}), len(rows))
        unknown = [r for r in rows if r["price"]["status"] not in {"confirmed", "fixture"}
                   or r["hours_status"] not in {"confirmed", "fixture"}]
        self.assertTrue(unknown, "additional restaurants must retain unverified metadata")
        self.assertTrue(any(r["hours_status"] in {"confirmed", "fixture"} for r in rows))

    def test_verified_snapshot_has_resolvable_core_venues(self):
        for venue_id in ("venue:polin", "venue:kopernik", "venue:msn", "venue:muzeum-warszawy"):
            venue = self.catalog.venues[venue_id]
            self.assertIsNotNone(venue.get("lat"), venue_id)
            self.assertIsNotNone(venue.get("lon"), venue_id)

    def test_2026_event_refresh_has_real_future_dates_and_explicit_unknowns(self):
        expected = [
            ("2026-10-27", "event:msn-seniors-guided-tour-2026-10-27", "13:00"),
            ("2026-10-29", "event:fado-gala-relax-2026-10-29", "20:00"),
            ("2026-11-04", "event:nigel-kennedy-2026-11-04", "20:00"),
            ("2026-11-08", "event:fryderyk-chopin-recital-2026-11-08", "17:00"),
        ]
        self.assertEqual(self.catalog.payload["coverage"]["last_manual_refresh"], "2026-10-14")
        for when, event_id, start in expected:
            rows = self.catalog.activities_for_date(date.fromisoformat(when))
            row = next(x for x in rows if x["id"] == event_id)
            self.assertTrue(row["schedulable"], event_id)
            self.assertEqual(row["start_time"], start)
            self.assertIsNotNone(row["venue"].get("lat"), event_id)
            self.assertIsNotNone(row["venue"].get("lon"), event_id)
            self.assertEqual(row["availability"], "unknown", event_id)
            self.assertEqual(row["price"]["status"], "unknown", event_id)
            self.assertTrue(row["info_url"].startswith("https://"), event_id)

        no_time = next(x for x in self.catalog.activities_for_date(date(2026, 11, 9))
                       if x["id"] == "event:yamato-roma-2026-11-09")
        self.assertFalse(no_time["schedulable"])
        self.assertIsNone(no_time["start_time"])
        self.assertIn("not verified", no_time["unschedulable_reason"])

    def test_future_dated_official_recital_is_plannable_with_unknown_ticket_status(self):
        plan = DayPlanner(self.catalog).generate(
            brief(date="2026-11-08", start_time="13:00", end_time="21:30",
                  activity_count=1, include_meal=False,
                  must_include_ids=["event:fryderyk-chopin-recital-2026-11-08"])
        )["plans"][0]
        recital = next(x for x in plan["items"]
                       if x["activity_id"] == "event:fryderyk-chopin-recital-2026-11-08")
        self.assertEqual(recital["display_start"], "17:00")
        self.assertEqual(recital["source_event_end_status"], "confirmed")
        self.assertEqual(recital["availability"], "unknown")
        self.assertTrue(plan["checks"])

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
        arrival = _dt(date(2026, 10, 17), "18:30")
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
                "duration_minutes": 510,
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

    def test_reported_dinner_failure_replaces_only_dinner_and_keeps_concert(self):
        # User-reported unavailability is an explicit demo condition, never a live closure claim.
        chosen = brief(
            activity_count=3, include_meal=True,
            must_include_ids=["event:simple-plan-2026-10-17"],
            locked_ids=["event:simple-plan-2026-10-17"],
        )
        original = self.planner.generate(chosen)["plans"][0]
        original_restaurant = next(item for item in original["items"] if item["kind"] == "restaurant")
        locked_event = next(item for item in original["items"] if item["activity_id"] == "event:simple-plan-2026-10-17")
        result = self.planner.repair(original, chosen, original_restaurant["activity_id"])
        self.assertTrue(result["plans"], "demo must have a genuinely feasible alternative dinner")
        next_plan = result["plans"][0]
        ids = {item["activity_id"] for item in next_plan["items"]}
        self.assertNotIn(original_restaurant["activity_id"], ids)
        self.assertIn(locked_event["activity_id"], ids)
        next_event = next(item for item in next_plan["items"] if item["activity_id"] == locked_event["activity_id"])
        self.assertEqual(next_event["start"], locked_event["start"])
        self.assertEqual(next_plan["repair"]["removed"], original_restaurant["activity_id"])
        self.assertTrue(next_plan["repair"]["added_ids"])
        self.assertTrue(any(item["kind"] == "restaurant" for item in next_plan["items"]))

    def test_two_repeated_dinner_failures_preserve_locks_and_exclusions(self):
        b = brief(
            activity_count=3, include_meal=True,
            must_include_ids=["event:simple-plan-2026-10-17"],
            locked_ids=["event:simple-plan-2026-10-17"],
            budget_total=500,
        )
        initial = self.planner.generate(b)["plans"][0]
        first_restaurant = next(x["activity_id"] for x in initial["items"] if x["kind"] == "restaurant")
        locked_start = next(x["start"] for x in initial["items"]
                            if x["activity_id"] == "event:simple-plan-2026-10-17")
        first = self.planner.repair(initial, b, first_restaurant)
        self.assertTrue(first["plans"], "first replacement should exist for the demo")
        first_plan = first["plans"][0]
        second_restaurant = next(x["activity_id"] for x in first_plan["items"]
                                 if x["kind"] == "restaurant")
        self.assertNotEqual(first_restaurant, second_restaurant)
        after_first_brief = PlannerBrief.from_payload(first["brief"])
        second = self.planner.repair(first_plan, after_first_brief, second_restaurant)
        self.assertTrue(second["plans"], "second replacement should exist under the same locks")
        final = second["plans"][0]
        ids = {x["activity_id"] for x in final["items"]}
        self.assertNotIn(first_restaurant, ids)
        self.assertNotIn(second_restaurant, ids)
        self.assertIn(first_restaurant, second["brief"]["excluded_ids"])
        self.assertIn(second_restaurant, second["brief"]["excluded_ids"])
        concert = next(x for x in final["items"]
                       if x["activity_id"] == "event:simple-plan-2026-10-17")
        self.assertEqual(concert["start"], locked_start)
        self.assertEqual(final["repair"]["removed"], second_restaurant)
        self.assertEqual(len(final["repair"]["added_ids"]), 1)

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



class PlannerLiveTasteTests(unittest.TestCase):
    def test_planner_uses_verified_restaurant_only_qloo_ranks(self):
        from unstuck.providers import TasteResult, TasteResults

        class FakeProvider:
            mode = "live"

            def rank_with_context(self, places, taste_refs, *, failed_place):
                self.last_places = places
                return TasteResults(
                    [TasteResult(p.id, 0.9 if i == 0 else 0.6, i + 1, ("Radiohead",), "qloo")
                     for i, p in enumerate(places)],
                    trace={
                        "status": "live",
                        "insights_called": True,
                        "recognized_signals": [{"input": "Radiohead", "name": "Radiohead",
                                                 "entity_id": "artist:test", "kind": "taste_reference"}],
                    },
                )

        engine = build_engine("fixture", "real")
        provider = FakeProvider()
        planner = DayPlanner(PlannerCatalog(engine.places), provider)
        result = planner.generate(brief(activity_count=2, must_include_ids=[]))
        self.assertEqual(result["taste_status"], "live_restaurants")
        self.assertTrue(result["taste_audit"]["insights_called"])
        self.assertGreaterEqual(result["taste_audit"]["ranked_count"], 2)
        self.assertTrue(result["plans"])
        comparison = result["taste_audit"]["same_pool_comparison"]
        self.assertEqual(comparison["method"], "same_feasible_plan_pool")
        self.assertEqual(comparison["study_baseline"]["id"], comparison["baseline_top_plan_id"])
        self.assertEqual(comparison["study_with_qloo"]["id"], comparison["with_qloo_top_plan_id"])
        self.assertTrue(comparison["study_baseline"]["stops"])
        self.assertTrue(all("start" in stop and "end" in stop for stop in comparison["study_with_qloo"]["stops"]))
        self.assertEqual(comparison["study_baseline"]["budget_total"], comparison["study_with_qloo"]["budget_total"])
        self.assertEqual(comparison["with_qloo_top_plan_id"], result["plans"][0]["id"])
        operational = DayPlanner(planner.catalog).generate(brief(activity_count=2, must_include_ids=[]))
        self.assertEqual(comparison["baseline_top_plan_id"], operational["plans"][0]["id"])
        self.assertEqual(
            comparison["top_plan_changed"],
            comparison["baseline_top_plan_id"] != comparison["with_qloo_top_plan_id"],
        )
        self.assertTrue(any(item.get("taste_rank") is not None
                            for plan in result["plans"] for item in plan["items"]
                            if item["kind"] == "restaurant"))
        for plan in result["plans"]:
            self.assertIn("Concerts and museums", plan["taste_note"])

    def test_missing_planner_qloo_does_not_invent_live_taste(self):
        class UnavailableProvider:
            mode = "live"
            def rank_with_context(self, *_args, **_kwargs):
                raise RuntimeError("QLOO_RATE_WINDOW_EXHAUSTED")
        engine = build_engine("fixture", "real")
        planner = DayPlanner(PlannerCatalog(engine.places), UnavailableProvider())
        result = planner.generate(brief(activity_count=2))
        self.assertEqual(result["taste_status"], "unavailable")
        self.assertNotIn("same_pool_comparison", result["taste_audit"])
        self.assertTrue(result["plans"])
        self.assertTrue(all(not any(item.get("taste_rank") for item in p["items"])
                            for p in result["plans"]))


if __name__ == "__main__":
    unittest.main()
