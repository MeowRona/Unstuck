from __future__ import annotations

import json
import os
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from unstuck.engine import Evaluation, UnstuckEngine, _constraint_checks, estimate_travel_minutes, evaluate_place, pareto_front
from unstuck.models import Place, SearchBrief, SearchState
from unstuck.origins import LEGACY_ORIGINS, public_origin_payload, resolve_origin
from unstuck.providers import FixtureTasteProvider, NoTasteProvider, QlooTransport, RealQlooProvider, TasteResult, TasteResults


ROOT = Path(__file__).resolve().parents[1]


def brief(**overrides) -> SearchBrief:
    payload = {
        "original_plan": "Dinner and talk",
        "failed_place": "Closed Place",
        "failure_reason": "closed",
        "goal": "meal",
        "city": "Warsaw",
        "date": "2026-10-10",
        "start_time": "18:30",
        "return_by": "22:00",
        "min_stay_minutes": 75,
        "people": 2,
        "budget_total": 100,
        "currency": "PLN",
        "origin": "Warsaw Central",
        "travel_mode": "transit",
        "max_one_way_minutes": 18,
        "categories": ["restaurant"],
        "taste_refs": ["Amelie", "Radiohead"],
        "meal_required": True,
        "negotiable_extra_travel_minutes": 0,
        "negotiable_stay_reduction_minutes": 0,
        "allow_category_change": False,
    }
    payload.update(overrides)
    return SearchBrief.from_payload(payload)


def load_fixture_engine() -> UnstuckEngine:
    rows = json.loads((ROOT / "data" / "places_fixture.json").read_text(encoding="utf-8"))["places"]
    places = [Place.from_dict(row) for row in rows]
    provider = FixtureTasteProvider(ROOT / "data" / "taste_fixtures.json")
    return UnstuckEngine(places, provider)


class ConstraintTests(unittest.TestCase):
    def test_legacy_origin_still_resolves(self):
        self.assertEqual(resolve_origin("Warsaw Central"), LEGACY_ORIGINS["Warsaw Central"])

    def test_origin_resolution_is_diacritic_insensitive(self):
        self.assertEqual(resolve_origin("Metro Mlociny"), resolve_origin("Metro Młociny"))

    def test_unknown_origin_is_not_silently_replaced_with_city_centre(self):
        engine = load_fixture_engine()
        with self.assertRaisesRegex(ValueError, "Unknown start location"):
            engine.search(SearchState(brief(origin="Definitely not a real origin")))

    def test_origin_catalog_has_broad_district_coverage(self):
        payload = public_origin_payload()
        self.assertGreaterEqual(payload["count"], 120)
        self.assertEqual(len(payload["districts"]), 18)
        self.assertGreaterEqual(payload["districts"].get("Śródmieście", 0), 10)
        self.assertGreaterEqual(payload["districts"].get("Mokotów", 0), 8)
        self.assertGreaterEqual(payload["districts"].get("Ursynów", 0), 8)

    def test_origin_catalog_has_unique_coordinates_inside_warsaw_area(self):
        rows = public_origin_payload()["origins"]
        coords = {(round(float(row["lat"]), 5), round(float(row["lon"]), 5)) for row in rows}
        self.assertEqual(len(coords), len(rows))
        for row in rows:
            self.assertTrue(52.05 <= float(row["lat"]) <= 52.40)
            self.assertTrue(20.75 <= float(row["lon"]) <= 21.35)

    def test_remote_origin_changes_travel_estimate(self):
        place = load_fixture_engine().places[0]
        central = estimate_travel_minutes(brief(origin="Warsaw Central"), place)
        ml = estimate_travel_minutes(brief(origin="Metro Młociny"), place)
        self.assertGreater(ml, central)

    def test_travel_limit_allows_two_and_a_half_hours(self):
        self.assertEqual(brief(max_one_way_minutes=150).max_one_way_minutes, 150)
        with self.assertRaisesRegex(ValueError, "max_one_way_minutes must be between 5 and 150"):
            brief(max_one_way_minutes=151)

    def test_high_taste_never_beats_hard_budget(self):
        engine = load_fixture_engine()
        result = engine.search(SearchState(brief(budget_total=80, taste_refs=["Radiohead"])))
        self.assertTrue(result["cards"])
        for card in result["cards"]:
            if card["cost"]["max"] is not None:
                self.assertLessEqual(card["cost"]["max"], 80)

    def test_real_restaurant_cards_expose_google_place_id_only_as_identifier(self):
        rows = json.loads((ROOT / "data" / "places_warsaw.json").read_text(encoding="utf-8"))["places"]
        restaurants = [row for row in rows if row.get("category") == "restaurant"]
        self.assertEqual(sum(bool(row.get("google_place_id")) for row in restaurants), 5)
        for row in restaurants:
            if row.get("google_place_id"):
                self.assertTrue(str(row["google_place_id"]).startswith("ChIJ"))

    def test_cost_is_for_two_people(self):
        engine = load_fixture_engine()
        result = engine.search(SearchState(brief(budget_total=70)))
        names = {card["name"] for card in result["cards"]}
        self.assertNotIn("Quiet Table (demo)", names)  # 44 * 2 > 70

    def test_meal_requirement_excludes_cafe_and_gallery(self):
        engine = load_fixture_engine()
        result = engine.search(SearchState(brief(categories=[], taste_refs=["Amelie"])))
        names = {card["name"] for card in result["cards"]}
        self.assertNotIn("Garden Cafe (demo)", names)
        self.assertNotIn("Frame Gallery (demo)", names)

    def test_unknown_price_is_never_confirmed_pass(self):
        engine = load_fixture_engine()
        result = engine.search(SearchState(brief(budget_total=1, taste_refs=["Daft Punk"])))
        unknown_cards = [c for c in result["cards"] if c["id"] == "fixture:unknown-price"]
        if unknown_cards:
            card = unknown_cards[0]
            self.assertEqual(card["feasibility_status"], "requires_checking")
            budget = next(row for row in card["constraint_checks"] if row["field"] == "budget")
            self.assertEqual(budget["status"], "unknown")
            self.assertNotIn("Budget", card["keep"])
        self.assertNotEqual(result["result_status"], "confirmed")

    def test_rejected_place_does_not_return(self):
        engine = load_fixture_engine()
        state = SearchState(brief())
        first = engine.search(state)
        self.assertTrue(first["cards"])
        rejected = first["cards"][0]["id"]
        state.reject(rejected)
        second = engine.search(state)
        self.assertNotIn(rejected, {card["id"] for card in second["cards"]})

    def test_rejecting_first_three_yields_next_taste_layer(self):
        class StableTasteProvider:
            mode = "fixture"

            def rank(self, places, taste_refs):
                return [
                    TasteResult(
                        place_id=place.id,
                        affinity=1.0 - index * 0.05,
                        rank=index + 1,
                        evidence=("Amelie",),
                        source="fixture",
                    )
                    for index, place in enumerate(places)
                ]

        template = json.loads((ROOT / "data" / "places_fixture.json").read_text(encoding="utf-8"))["places"][0]
        places = []
        for index in range(12):
            row = dict(template)
            row["id"] = f"fixture:queue-{index:02d}"
            row["name"] = f"Queue Venue {index:02d}"
            row["lat"] = 52.231 + index * 0.00005
            row["lon"] = 21.0105 + index * 0.00005
            places.append(Place.from_dict(row))

        engine = UnstuckEngine(places, StableTasteProvider())
        state = SearchState(brief(budget_total=200, max_one_way_minutes=30))

        first = engine.search(state)
        self.assertEqual(len(first["cards"]), 3)
        first_ids = [card["id"] for card in first["cards"]]
        for place_id in first_ids:
            state.reject(place_id)

        second = engine.search(state)
        self.assertEqual(len(second["cards"]), 3)
        second_ids = [card["id"] for card in second["cards"]]
        self.assertTrue(set(first_ids).isdisjoint(second_ids))
        self.assertLess(
            max(card["taste"]["affinity"] for card in second["cards"]),
            min(card["taste"]["affinity"] for card in first["cards"]),
        )

        for place_id in second_ids:
            state.reject(place_id)
        third = engine.search(state)
        self.assertEqual(len(third["cards"]), 3)
        self.assertTrue(set(first_ids + second_ids).isdisjoint({card["id"] for card in third["cards"]}))

    def test_failed_place_name_is_excluded(self):
        engine = load_fixture_engine()
        result = engine.search(SearchState(brief(failed_place="Quiet Table (demo)")))
        self.assertNotIn("Quiet Table (demo)", {c["name"] for c in result["cards"]})

    def test_return_time_includes_outbound_stay_and_return(self):
        engine = load_fixture_engine()
        result = engine.search(SearchState(brief(return_by="19:45", min_stay_minutes=60)))
        self.assertTrue(result["empty"])

    def test_checked_route_can_expose_travel_and_stay_compromises_together(self):
        place = load_fixture_engine().places[0]
        ev = evaluate_place(
            place,
            brief(
                budget_total=500,
                max_one_way_minutes=25,
                min_stay_minutes=75,
                return_by="23:30",
            ),
            TasteResult(place.id, 0.8, 1, ("Amelie",), "fixture"),
            allowed_travel_minutes=35,
            stay_minutes=60,
            category_relaxed=False,
            route_override={
                "outbound_minutes": 28,
                "return_minutes": 30,
                "source": "Warsaw GTFS schedule",
                "checked_at": "2026-10-05T12:00:00+00:00",
                "realtime": False,
            },
        )
        fields = {change["field"] for change in ev.changes}
        self.assertEqual(fields, {"one-way travel", "minimum stay"})
        travel = next(change for change in ev.changes if change["field"] == "one-way travel")
        self.assertEqual(travel["delta"], 5)
        self.assertEqual(travel["outbound_minutes"], 28)
        self.assertEqual(travel["return_minutes"], 30)

    def test_checked_return_route_can_break_locked_return_time(self):
        place = load_fixture_engine().places[0]
        ev = evaluate_place(
            place,
            brief(
                budget_total=500,
                max_one_way_minutes=35,
                min_stay_minutes=60,
                start_time="18:30",
                return_by="20:00",
            ),
            None,
            allowed_travel_minutes=35,
            stay_minutes=60,
            category_relaxed=False,
            route_override={
                "outbound_minutes": 10,
                "return_minutes": 25,
                "source": "Warsaw GTFS schedule",
                "checked_at": "2026-10-05T12:00:00+00:00",
            },
        )
        self.assertFalse(ev.viable)
        self.assertTrue(any("return" in reason.lower() for reason in ev.hard_failures))

    def test_unchecked_routes_are_unknown_not_preserved(self):
        place = load_fixture_engine().places[0]
        ev = evaluate_place(
            place,
            brief(budget_total=500, max_one_way_minutes=30, return_by="23:30"),
            None,
            allowed_travel_minutes=30,
            stay_minutes=75,
            category_relaxed=False,
        )
        checks = {row["field"]: row for row in _constraint_checks(ev, brief(budget_total=500, max_one_way_minutes=30, return_by="23:30"))}
        self.assertEqual(checks["one-way travel"]["status"], "unknown")
        self.assertEqual(checks["return"]["status"], "unknown")
        self.assertNotIn("Travel limit", ev.preserved)
        self.assertNotIn("Return time", ev.preserved)

    def test_rejection_reason_and_undo_are_session_state_only(self):
        state = SearchState(brief())
        state.reject("fixture:a", "too_far")
        self.assertIn("fixture:a", state.rejected_ids)
        self.assertEqual(state.rejection_history[-1]["reason"], "too_far")
        restored = state.undo_reject()
        self.assertEqual(restored["place_id"], "fixture:a")
        self.assertNotIn("fixture:a", state.rejected_ids)
        self.assertEqual(state.rejection_history, [])

    def test_explicit_extra_travel_changes_strategy(self):
        engine = load_fixture_engine()
        strict = engine.search(SearchState(brief(max_one_way_minutes=8, budget_total=100)))
        relaxed = engine.search(
            SearchState(brief(max_one_way_minutes=8, negotiable_extra_travel_minutes=12, budget_total=100))
        )
        self.assertLessEqual(len(strict["cards"]), len(relaxed["cards"]))
        self.assertTrue(any("trying the next" in x.lower() for x in relaxed["agent_log"]) or relaxed["strategy_used"] == "strict")

    def test_case_requiring_two_allowed_compromises(self):
        engine = load_fixture_engine()
        result = engine.search(
            SearchState(
                brief(
                    max_one_way_minutes=5,
                    return_by="19:55",
                    min_stay_minutes=75,
                    negotiable_extra_travel_minutes=3,
                    negotiable_stay_reduction_minutes=10,
                    taste_refs=["Amelie"],
                )
            )
        )
        self.assertEqual(result["strategy_used"], "shorter_stay")
        self.assertTrue(result["cards"])
        fields = {change["field"] for change in result["cards"][0]["change"]}
        self.assertIn("one-way travel", fields)
        self.assertIn("minimum stay", fields)

    def test_budget_change_recomputes_without_forgetting_state(self):
        engine = load_fixture_engine()
        state = SearchState(brief(budget_total=80, taste_refs=["Amelie"]))
        first = engine.search(state)
        self.assertNotIn("Quiet Table (demo)", {card["name"] for card in first["cards"]})
        state.update_brief({"budget_total": 100})
        second = engine.search(state)
        self.assertEqual(second["round"], 2)
        self.assertIn("Quiet Table (demo)", {card["name"] for card in second["cards"]})

    def test_rescue_search_does_not_prefilter_named_dish_when_quote_exceeds_budget(self):
        base = load_fixture_engine().places[0]
        only_dish = replace(
            base, id="dish-price-only", name="Dish Price Only",
            price=replace(
                base.price, minimum=49, maximum=49, unit="PLN",
                status="confirmed", basis="per_person_dish_only"
            ),
            hours_status="confirmed",
            hours={str(day): (("10:00", "23:30"),) for day in range(7)}
        )
        real_meal_above_budget = replace(
            only_dish, id="confirmed-meal-over-budget", name="Meal Above Budget",
            price=replace(only_dish.price, basis="per_person")
        )
        sample = brief(
            failed_place="", budget_total=80, people=2, taste_refs=[],
            origin_lat=only_dish.lat, origin_lon=only_dish.lon,
            max_one_way_minutes=120, return_by="23:30",
            min_stay_minutes=45
        )
        engine = UnstuckEngine([only_dish, real_meal_above_budget], NoTasteProvider())
        result = engine.search(SearchState(sample))
        self.assertTrue(result["cards"], result.get("explanation"))
        names = {card["name"] for card in result["cards"]}
        self.assertIn("Dish Price Only", names)
        self.assertNotIn("Meal Above Budget", names)
        card = next(card for card in result["cards"] if card["name"] == "Dish Price Only")
        self.assertEqual(card["feasibility_status"], "requires_checking")
        self.assertIsNone(card["estimated_total_min"] if "estimated_total_min" in card else card["cost"]["min"])
        self.assertTrue(any(
            "not a verified minimum" in str(msg) for msg in card["needs_checking"]
        ))

    def test_live_shortlist_keeps_named_dish_as_budget_unknown(self):
        base = load_fixture_engine().places[0]
        only_dish = replace(
            base, id="dish-only-live", name="Dish Only Live",
            price=replace(base.price, minimum=49, maximum=49, unit="PLN",
                          status="confirmed", basis="per_person_dish_only"),
            hours_status="confirmed",
            hours={str(day): (("10:00", "23:30"),) for day in range(7)}
        )
        class RecordingProvider:
            mode = "live"
            def __init__(self):
                self.received = []
            def rank_with_context(self, places, refs, *, failed_place):
                self.received.append([place.id for place in places])
                return TasteResults(
                    [TasteResult(place.id, None, None, (), "qloo") for place in places],
                    trace={"status": "no_coverage", "insights_called": False},
                )
        recorder = RecordingProvider()
        engine = UnstuckEngine([only_dish], recorder)
        result = engine.search(SearchState(brief(
            failed_place="", budget_total=80, people=2, taste_refs=[],
            origin_lat=only_dish.lat, origin_lon=only_dish.lon,
            max_one_way_minutes=120, min_stay_minutes=45, return_by="23:30",
        )))
        self.assertEqual(recorder.received, [["dish-only-live"]])
        self.assertTrue(result["cards"])
        self.assertEqual(result["cards"][0]["feasibility_status"], "requires_checking")

    def test_named_menu_dish_never_confirms_whole_meal_budget(self):
        base = load_fixture_engine().places[0]
        dish = replace(base, price=replace(
            base.price, minimum=49, maximum=49, status="confirmed",
            basis="per_person_dish_only",
        ))
        sample = brief(failed_place="", budget_total=120, people=2,
                       origin_lat=dish.lat, origin_lon=dish.lon,
                       return_by="23:30", taste_refs=[])
        ev = evaluate_place(dish, sample, None, allowed_travel_minutes=120,
                            stay_minutes=75, category_relaxed=False)
        self.assertTrue(ev.viable)
        self.assertFalse(ev.confirmed)
        self.assertIsNone(ev.estimated_total_min)
        self.assertIsNone(ev.estimated_total_max)
        self.assertNotIn("Budget", ev.preserved)
        self.assertTrue(any("Published example" in reason for reason in ev.needs_checking))
        budget = next(x for x in _constraint_checks(ev, sample) if x["field"] == "budget")
        self.assertEqual(budget["status"], "unknown")

        over_budget = evaluate_place(
            dish, brief(failed_place="", budget_total=90, people=2,
                        origin_lat=dish.lat, origin_lon=dish.lon,
                        return_by="23:30", taste_refs=[]),
            None, allowed_travel_minutes=120, stay_minutes=75, category_relaxed=False,
        )
        self.assertTrue(over_budget.viable, "a dish above budget cannot exclude cheaper menu choices")
        self.assertFalse(over_budget.confirmed)
        self.assertIsNone(over_budget.estimated_total_min)
        self.assertIsNone(over_budget.estimated_total_max)
        self.assertFalse(any("budget" in reason.lower() for reason in over_budget.hard_failures))
        self.assertTrue(any("not a verified minimum" in reason for reason in over_budget.needs_checking))

    def test_estimated_hours_are_not_confirmed(self):
        engine = load_fixture_engine()
        row = json.loads((ROOT / "data" / "places_fixture.json").read_text(encoding="utf-8"))["places"][0]
        row["hours_status"] = "estimated"
        place = Place.from_dict(row)
        taste = TasteResult(place.id, 1.0, 1, ("Amelie",), "fixture")
        ev = evaluate_place(place, brief(), taste, allowed_travel_minutes=18, stay_minutes=75, category_relaxed=False)
        self.assertTrue(ev.viable)
        self.assertFalse(ev.confirmed)
        self.assertTrue(any("estimated" in item.lower() for item in ev.needs_checking))

    def test_date_exception_can_close_normally_open_place(self):
        row = json.loads((ROOT / "data" / "places_fixture.json").read_text(encoding="utf-8"))["places"][0]
        row["date_exceptions"] = {"2026-10-10": []}
        place = Place.from_dict(row)
        ev = evaluate_place(place, brief(), None, allowed_travel_minutes=18, stay_minutes=75, category_relaxed=False)
        self.assertTrue(any("hours" in item.lower() for item in ev.hard_failures))

    def test_cross_midnight_hours_are_supported(self):
        row = json.loads((ROOT / "data" / "places_fixture.json").read_text(encoding="utf-8"))["places"][0]
        row["hours"] = {"4": [["18:00", "02:00"]]}
        place = Place.from_dict(row)
        b = brief(date="2026-10-09", start_time="23:00", return_by="02:30", min_stay_minutes=90, max_one_way_minutes=30)
        ev = evaluate_place(place, b, None, allowed_travel_minutes=30, stay_minutes=90, category_relaxed=False)
        self.assertFalse(any("hours" in item.lower() for item in ev.hard_failures))


    def test_fixed_sixty_second_demo_requires_a_real_allowed_compromise(self):
        rows = json.loads((ROOT / "data" / "places_warsaw.json").read_text(encoding="utf-8"))["places"]
        engine = UnstuckEngine(
            [Place.from_dict(row) for row in rows],
            FixtureTasteProvider(ROOT / "data" / "taste_fixtures.json"),
        )
        origins = json.loads((ROOT / "data" / "origins_warsaw.json").read_text(encoding="utf-8"))["origins"]
        demo_origin = next(row for row in origins if row["id"] == "warsaw:srodmiescie:warszawa-centralna")
        result = engine.search(
            SearchState(
                brief(
                    original_plan="Dinner at HOŻA Steakhouse",
                    failed_place="HOŻA Steakhouse",
                    failure_reason="unavailable",
                    origin=demo_origin["label"],
                    origin_lat=demo_origin["lat"],
                    origin_lon=demo_origin["lon"],
                    date="2026-10-09",
                    start_time="18:30",
                    return_by="20:45",
                    min_stay_minutes=120,
                    max_one_way_minutes=25,
                    budget_total=200,
                    negotiable_extra_travel_minutes=0,
                    negotiable_stay_reduction_minutes=30,
                )
            )
        )
        self.assertTrue(result["cards"])
        self.assertEqual(result["strategy_used"], "shorter_stay")
        self.assertTrue(
            all(any(change["field"] == "minimum stay" for change in card["change"]) for card in result["cards"])
        )
        self.assertNotIn("HOŻA Steakhouse", {card["name"] for card in result["cards"]})
        self.assertEqual(result["taste_audit"]["status"], "fixture_preview")
        self.assertEqual(result["taste_audit"]["ranked_order"], [])



class MinimalityTests(unittest.TestCase):
    def _evaluation(self, changes):
        place = load_fixture_engine().places[0]
        now = datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc)
        return Evaluation(
            place=place,
            affinity=0.5,
            taste_rank=1,
            taste_evidence=(),
            taste_source="fixture",
            travel_minutes=10,
            stay_minutes=60,
            arrival=now,
            departure=now,
            return_time=now,
            estimated_total_min=50,
            estimated_total_max=70,
            hard_failures=(),
            needs_checking=(),
            changes=tuple(changes),
            preserved=(),
        )

    def test_pareto_removes_dominated_compromise(self):
        small = self._evaluation([{"field": "one-way travel", "delta": 5}])
        dominated = self._evaluation([{"field": "one-way travel", "delta": 9}])
        incomparable = self._evaluation([{"field": "minimum stay", "delta": 5}])
        front = pareto_front([small, dominated, incomparable])
        self.assertIn(small, front)
        self.assertIn(incomparable, front)
        self.assertNotIn(dominated, front)

    def test_pareto_matches_bruteforce_definition(self):
        candidates = [
            self._evaluation([]),
            self._evaluation([{"field": "one-way travel", "delta": 4}]),
            self._evaluation([{"field": "minimum stay", "delta": 7}]),
            self._evaluation([{"field": "category", "from": "restaurant", "to": "cafe"}]),
        ]
        front = pareto_front(candidates)
        self.assertEqual(front, [candidates[0]])


class QlooContractTests(unittest.TestCase):
    def test_fixture_trace_never_claims_failed_place_anchor_was_qloo_resolved(self):
        engine = load_fixture_engine()
        ranked = engine.taste_provider.rank_with_context(
            engine.places[:3],
            ["Amelie"],
            failed_place="Closed Place",
        )
        self.assertEqual(ranked.trace["status"], "fixture_preview")
        self.assertFalse(ranked.trace["anchor_used"])
        self.assertEqual(ranked.trace["failed_place_anchor"], "Closed Place")

    def test_no_taste_baseline_has_no_affinity_signal(self):
        engine = load_fixture_engine()
        ranked = NoTasteProvider().rank(engine.places[:2], ["Amelie"])
        self.assertEqual([row.source for row in ranked], ["baseline", "baseline"])
        self.assertTrue(all(row.affinity is None for row in ranked))

    def test_missing_key_is_blocked_not_fixture_pass(self):
        old = os.environ.pop("QLOO_API_KEY", None)
        try:
            with self.assertRaisesRegex(RuntimeError, "BLOCKED_NO_API_KEY"):
                QlooTransport()
        finally:
            if old is not None:
                os.environ["QLOO_API_KEY"] = old

    def test_public_entity_picker_has_an_independent_rolling_quota(self):
        class FakeTransport:
            def request_scope(self, max_calls=18):
                from contextlib import nullcontext
                return nullcontext()
            def get_json(self, path, params=None):
                return {"results": []}
        provider = RealQlooProvider(FakeTransport())
        with patch("unstuck.providers.time.monotonic", side_effect=(
            [100] * 12 + [100] + [161] * 12 +
            [222] * 12 + [283] * 12 + [344] * 12 + [405] * 12 +
            [466, 3701]
        )):
            for _ in range(12):
                self.assertEqual(provider.suggest_taste_entities("Radiohead", "artist"), [])
            with self.assertRaisesRegex(RuntimeError, "QLOO_PICKER_RATE_LIMITED"):
                provider.suggest_taste_entities("Another", "artist")
            # A minute later the short window renews; later batches consume
            # the independent 72/h public-lookup ceiling.
            for _batch in range(5):
                for _ in range(12):
                    provider.suggest_taste_entities("Different", "movie")
            with self.assertRaisesRegex(RuntimeError, "QLOO_PICKER_RATE_LIMITED"):
                provider.suggest_taste_entities("Beyond hourly cap", "movie")
            self.assertEqual(provider.suggest_taste_entities("After the window", "book"), [])

    def test_good_for_both_uses_independent_same_pool_ranks_and_minimax(self):
        class FakeTransport:
            pass
        class TwoProfileProvider(RealQlooProvider):
            def __init__(self):
                super().__init__(FakeTransport())
                self.calls = []
            def rank_with_context(self, places, taste_refs, *, failed_place):
                self.calls.append((tuple(p.id for p in places), tuple(taste_refs), failed_place))
                ranks = ([1, 3, 2] if list(taste_refs) == ["A"] else [3, 1, 2])
                return TasteResults(
                    [TasteResult(p.id, None, ranks[i], (), "qloo") for i, p in enumerate(places)],
                    trace={
                        "status": "live", "insights_called": True,
                        "candidate_entity_count": len(places),
                        "recognized_signals": [{"input": taste_refs[0], "name": taste_refs[0],
                                                 "entity_id": taste_refs[0], "kind": "taste_reference"}],
                    },
                )
        original = load_fixture_engine().places[0]
        places = [replace(original, id=code) for code in ["alpha", "beta", "gamma"]]
        provider = TwoProfileProvider()
        both = provider.rank_pair_with_context(places, ["A"], ["B"], failed_place="Closed")
        self.assertEqual(both.trace["status"], "live")
        self.assertEqual(both.trace["pair_status"], "verified")
        self.assertEqual(both.trace["ranked_entity_count"], 3)
        self.assertEqual(both.trace["pair_positions"][0],
                         {"place_id": "gamma", "person_a_rank": 2,
                          "person_b_rank": 2, "compromise_rank": 1})
        self.assertEqual(next(x.rank for x in both if x.place_id == "gamma"), 1)
        self.assertTrue(all(x.affinity is None for x in both))
        self.assertEqual(provider.calls[0][0], provider.calls[1][0])
        self.assertEqual([x[1] for x in provider.calls], [("A",), ("B",)])
        self.assertEqual([x[2] for x in provider.calls], [None, None])

    def test_good_for_both_refuses_unverified_pair_and_skips_second_if_first_weak(self):
        class WeakProvider(RealQlooProvider):
            def __init__(self):
                super().__init__(object())
                self.calls = []
            def rank_with_context(self, places, taste_refs, *, failed_place):
                self.calls.append(tuple(taste_refs))
                return TasteResults(
                    [TasteResult(p.id, None, 1 if i == 0 else None, (), "qloo")
                     for i, p in enumerate(places)],
                    trace={"status": "live", "insights_called": True,
                           "candidate_entity_count": len(places)},
                )
        places = load_fixture_engine().places[:3]
        provider = WeakProvider()
        result = provider.rank_pair_with_context(places, ["A"], ["B"], failed_place=None)
        self.assertEqual(result.trace["status"], "no_coverage")
        self.assertEqual(result.trace["pair_status"], "insufficient_coverage")
        self.assertEqual(provider.calls, [("A",)])
        self.assertTrue(all(x.rank is None for x in result))

    def test_two_person_profile_validates_bounds_and_round_trips(self):
        good = brief(taste_refs=["artist: A", "movie: B"],
                     second_taste_refs=["artist: C", "movie: D"])
        self.assertEqual(good.second_taste_refs, ("artist: C", "movie: D"))
        self.assertEqual(SearchBrief.from_payload(good.to_dict()), good)
        for first, second in [
            (["A", "B", "C"], ["D"]),
            (["A"], ["B", "C", "D"]),
            ([], ["B"]),
        ]:
            with self.assertRaisesRegex(ValueError, "Good for both"):
                brief(taste_refs=first, second_taste_refs=second)

    def test_taste_picker_uses_one_typed_api_search_with_no_autoselection(self):
        class SearchTransport:
            def __init__(self):
                self.calls = []
                self.scopes = []
            def request_scope(self, max_calls=18):
                from contextlib import nullcontext
                self.scopes.append(max_calls)
                return nullcontext()
            def get_json(self, path, params=None):
                self.calls.append((path, params))
                return {"results": [
                    {"entity_id": "artist:first", "name": "Same Name",
                     "types": ["urn:entity:artist"]},
                    {"entity_id": "artist:second", "name": "Same Name",
                     "types": ["urn:entity:artist"]},
                    {"entity_id": "book:wrong", "name": "Same Name",
                     "types": ["urn:entity:book"]},
                    {"entity_id": "artist:first", "name": "Same Name",
                     "types": ["urn:entity:artist"]},
                ]}
        fake = SearchTransport()
        provider = RealQlooProvider(fake)
        options = provider.suggest_taste_entities("Same Name", "artist")
        self.assertEqual([x["id"] for x in options], ["artist:first", "artist:second"])
        self.assertEqual(fake.scopes, [1])
        self.assertEqual(fake.calls, [
            ("/search", {"query": "Same Name", "types": "urn:entity:artist", "take": 6})
        ])
        self.assertEqual(provider.resolve_interest("qloo-id:artist:second|artist|Same Name"),
                         ("artist:second", "Same Name"))
        self.assertEqual(len(fake.calls), 1, "chosen entity must bypass repeated ambiguous search")

    def test_taste_picker_rejects_invalid_or_control_character_ids(self):
        class SearchTransport:
            def request_scope(self, max_calls=18):
                from contextlib import nullcontext
                return nullcontext()
            def get_json(self, path, params=None):
                raise RuntimeError("QLOO_HTTP_404")
        provider = RealQlooProvider(SearchTransport())
        self.assertEqual(provider.suggest_taste_entities("Unknown", "movie"), [])
        for invalid in (
            "qloo-id:abc,def|artist|Name",
            "qloo-id:abc|restaurant|Name",
            "qloo-id:abc|artist|New\nline",
            "qloo-id:abc",
        ):
            with self.assertRaisesRegex(ValueError, "Invalid selected Qloo entity"):
                provider.resolve_interest(invalid)
        with self.assertRaisesRegex(ValueError, "taste type"):
            provider.suggest_taste_entities("Hello", "place")
        with self.assertRaisesRegex(ValueError, "2–70"):
            provider.suggest_taste_entities("X" * 71, "artist")

    def test_explicit_cultural_domain_disambiguates_without_guessing(self):
        class FakeTransport:
            def __init__(self):
                self.calls = []
            def get_json(self, path, params=None):
                self.calls.append((path, dict(params or {})))
                return {"results": [
                    {"entity_id": "artist:radiohead", "name": "Radiohead",
                     "types": ["urn:entity:artist"]},
                    {"entity_id": "book:radiohead", "name": "Radiohead",
                     "types": ["urn:entity:book"]},
                ]}
        fake = FakeTransport()
        provider = RealQlooProvider(fake)
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            provider.resolve_interest("Radiohead")
        entity_id, resolved = provider.resolve_interest("artist: Radiohead")
        self.assertEqual((entity_id, resolved), ("artist:radiohead", "Radiohead"))
        self.assertEqual(fake.calls[-1][1]["query"], "Radiohead")
        self.assertEqual(fake.calls[-1][1]["types"], "urn:entity:artist")

    def test_duplicate_search_rows_for_same_entity_are_not_ambiguous(self):
        class DuplicateTransport:
            def get_json(self, path, params=None):
                return {"results": [
                    {"entity_id": "artist:radiohead", "name": "Radiohead",
                     "types": ["urn:entity:artist"]},
                    {"entity_id": "artist:radiohead", "name": "Radiohead",
                     "types": ["urn:entity:artist"]},
                ]}
        provider = RealQlooProvider(DuplicateTransport())
        self.assertEqual(provider.resolve_interest("Radiohead")[0], "artist:radiohead")

    def test_qloo_404_unknown_interest_skips_unusable_venue_searches(self):
        class MissingSeedTransport:
            def __init__(self):
                self.calls = []
            def get_json(self, path, params=None):
                self.calls.append((path, dict(params or {})))
                raise RuntimeError("QLOO_HTTP_404")

        transport = MissingSeedTransport()
        provider = RealQlooProvider(transport)
        places = load_fixture_engine().places[:6]
        ranked = provider.rank_with_context(places, ["film: Unknown Fake Movie"], failed_place=None)
        self.assertEqual(ranked.trace["status"], "no_coverage")
        self.assertFalse(ranked.trace["insights_called"])
        self.assertEqual(len(ranked.trace["unresolved_signals"]), 1)
        self.assertEqual(ranked.trace["candidate_entity_count"], 0)
        self.assertEqual(len(transport.calls), 1, "must not spend quota on unusable venue resolution")
        self.assertTrue(all(r.rank is None for r in ranked))

    def test_qloo_404_missing_venue_preserves_usable_plan(self):
        class MissingVenueTransport:
            def __init__(self):
                self.calls = []
            def get_json(self, path, params=None):
                self.calls.append((path, dict(params or {})))
                if params.get("types") == "urn:entity:place":
                    raise RuntimeError("QLOO_HTTP_404")
                return {"results": [{"entity_id": "movie:blade-runner", "name": "Blade Runner",
                                    "types": ["urn:entity:movie"]}]}

        transport = MissingVenueTransport()
        provider = RealQlooProvider(transport)
        place = replace(load_fixture_engine().places[0], qloo_entity_id=None)
        ranked = provider.rank_with_context([place], ["film: Blade Runner"], failed_place=None)
        self.assertEqual(ranked.trace["status"], "no_coverage")
        self.assertEqual(ranked.trace["recognized_signals"][0]["name"], "Blade Runner")
        self.assertEqual(ranked.trace["unresolved_candidate_ids"], [place.id])
        self.assertFalse(ranked.trace["insights_called"])
        self.assertEqual(len(transport.calls), 2)
        self.assertIsNone(ranked[0].rank)

    def test_live_pool_excludes_closed_places_before_using_qloo_slots(self):
        from unstuck.providers import TasteResults
        base = load_fixture_engine().places[0]
        good = replace(
            base, id="valid", name="Open Place",
            hours_status="confirmed",
            hours={str(d): (("11:00", "23:30"),) for d in range(7)},
        )
        bad = replace(
            good, id="closed", name="Closed For Date",
            hours={str(d): tuple() for d in range(7)},
        )
        class Recorder:
            mode = "live"
            def __init__(self):
                self.received = []
            def rank_with_context(self, places, refs, *, failed_place):
                self.received.append([p.id for p in places])
                return TasteResults(
                    [TasteResult(p.id, None, None, (), "qloo") for p in places],
                    trace={"status": "no_coverage", "insights_called": False},
                )
        recorder = Recorder()
        engine = UnstuckEngine([bad, good], recorder)
        engine.search(SearchState(brief(
            failed_place="", budget_total=10000, taste_refs=[],
            origin_lat=good.lat, origin_lon=good.lon,
            max_one_way_minutes=120, min_stay_minutes=30,
        )))
        self.assertEqual(recorder.received, [["valid"]])

    def test_same_pool_ranking_uses_place_filter(self):
        class FakeTransport:
            def __init__(self):
                self.calls = []

            def get_json(self, path, params=None):
                self.calls.append((path, params or {}))
                if path == "/search":
                    q = params["query"]
                    if params.get("types") == "urn:entity:place":
                        return {"results": [{"entity_id": f"place:{q}", "name": q, "types": ["urn:entity:place"]}]}
                    return {"results": [{"entity_id": f"interest:{q}", "name": q, "types": ["urn:entity:movie"]}]}
                ids = params["filter.results.entities"].split(",")
                return {"results": {"entities": [{"entity_id": entity_id, "name": entity_id, "query": {"affinity": 0.8 - i * 0.1, "explainability": {"signals": ["interest:Blade Runner"]}}} for i, entity_id in enumerate(ids)]}}

        rows = json.loads((ROOT / "data" / "places_fixture.json").read_text(encoding="utf-8"))["places"][:2]
        places = [Place.from_dict(row) for row in rows]
        fake = FakeTransport()
        provider = RealQlooProvider(fake)
        ranked = provider.rank(places, ["Blade Runner"])
        insights = [params for path, params in fake.calls if path == "/v2/insights"]
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["filter.type"], "urn:entity:place")
        self.assertEqual(len(insights[0]["filter.results.entities"].split(",")), 2)
        self.assertEqual({r.place_id for r in ranked}, {p.id for p in places})
        self.assertTrue(all("Blade Runner" in r.evidence for r in ranked))

    def test_transport_cache_avoids_duplicate_network_call(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _limit):
                return b'{"results": []}'

        transport = QlooTransport(api_key="test-key", max_network_calls=2, cache_ttl_seconds=300)
        with patch("unstuck.providers.urlopen", return_value=Response()) as mocked:
            first = transport.get_json("/search", {"query": "x"})
            second = transport.get_json("/search", {"query": "x"})
        self.assertEqual(first, second)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(transport.network_calls, 1)

    def test_transport_call_budget_stops_before_extra_request(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _limit):
                return b'{"results": []}'

        transport = QlooTransport(api_key="test-key", max_network_calls=1, cache_ttl_seconds=0)
        with patch("unstuck.providers.urlopen", return_value=Response()) as mocked:
            transport.get_json("/search", {"query": "first"})
            with self.assertRaisesRegex(RuntimeError, "QLOO_RATE_WINDOW_EXHAUSTED"):
                transport.get_json("/search", {"query": "second"})
        self.assertEqual(mocked.call_count, 1)


    def test_rolling_window_recovers_without_restart(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _limit):
                return b'{"results":[]}'
        transport = QlooTransport(api_key="test-key", max_network_calls=1, cache_ttl_seconds=0, window_seconds=60)
        with patch("unstuck.providers.urlopen", return_value=Response()) as mocked, patch("unstuck.providers.time.monotonic", side_effect=[100, 100, 100, 100, 161, 161]):
            transport.get_json("/search", {"query": "first"})
            with self.assertRaisesRegex(RuntimeError, "QLOO_RATE_WINDOW_EXHAUSTED"):
                transport.get_json("/search", {"query": "blocked"})
            transport.get_json("/search", {"query": "after-window"})
        self.assertEqual(mocked.call_count, 2)

    def test_job_budget_resets_and_does_not_depend_on_lifetime(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _limit):
                return b'{"results":[]}'
        transport = QlooTransport(api_key="test-key", max_network_calls=10, cache_ttl_seconds=0)
        with patch("unstuck.providers.urlopen", return_value=Response()) as mocked:
            with transport.request_scope(max_calls=1):
                transport.get_json("/search", {"query": "first"})
                with self.assertRaisesRegex(RuntimeError, "QLOO_JOB_BUDGET_EXHAUSTED"):
                    transport.get_json("/search", {"query": "second"})
            with transport.request_scope(max_calls=1):
                transport.get_json("/search", {"query": "third"})
        self.assertEqual(mocked.call_count, 2)

    def test_live_provider_error_keeps_operational_results_and_truthful_trace(self):
        class BrokenProvider:
            mode = "live"
            def rank_with_context(self, *_args, **_kwargs):
                raise RuntimeError("QLOO_RATE_WINDOW_EXHAUSTED")
        engine = load_fixture_engine()
        engine.taste_provider = BrokenProvider()
        result = engine.search(SearchState(brief()))
        self.assertEqual(result["taste_audit"]["status"], "unavailable")
        self.assertFalse(result["taste_audit"]["insights_called"])
        self.assertTrue(result["cards"])

    def test_shorter_stay_uses_minimum_needed_not_maximum_allowed(self):
        engine = load_fixture_engine()
        original = brief(failed_place="", taste_refs=[], min_stay_minutes=75,
                         negotiable_stay_reduction_minutes=30, max_one_way_minutes=60,
                         budget_total=1000)
        travel = estimate_travel_minutes(original, engine.places[0])
        # Exactly five minutes short of the original target, with ample travel allowance.
        from datetime import timedelta
        deadline = (datetime.strptime(original.start_time, "%H:%M") +
                    timedelta(minutes=2 * travel + 70)).strftime("%H:%M")
        adjusted = brief(failed_place="", taste_refs=[], min_stay_minutes=75,
                         negotiable_stay_reduction_minutes=30, max_one_way_minutes=60,
                         budget_total=1000, return_by=deadline)
        result = engine.search(SearchState(adjusted))
        self.assertTrue(result["cards"])
        stay_changes = [change["delta"] for card in result["cards"]
                        for change in card["change"] if change["field"] == "minimum stay"]
        self.assertTrue(stay_changes)
        self.assertTrue(all(0 < delta <= 30 for delta in stay_changes))
        self.assertIn(5, stay_changes)


if __name__ == "__main__":
    unittest.main()
