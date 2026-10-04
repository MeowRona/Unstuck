from __future__ import annotations

import json
import os
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from unstuck.engine import Evaluation, UnstuckEngine, estimate_travel_minutes, evaluate_place, pareto_front
from unstuck.models import Place, SearchBrief, SearchState
from unstuck.origins import LEGACY_ORIGINS, public_origin_payload, resolve_origin
from unstuck.providers import FixtureTasteProvider, NoTasteProvider, QlooTransport, RealQlooProvider, TasteResult


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
            self.assertEqual(unknown_cards[0]["feasibility_status"], "requires_checking")
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
            with self.assertRaisesRegex(RuntimeError, "QLOO_CALL_BUDGET_EXHAUSTED"):
                transport.get_json("/search", {"query": "second"})
        self.assertEqual(mocked.call_count, 1)


if __name__ == "__main__":
    unittest.main()
