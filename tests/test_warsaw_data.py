from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from app import build_engine
from unstuck.geocoding import address_index, geocoder, street_index
from unstuck.models import SearchBrief, SearchState
from unstuck.providers import TasteResult
from unstuck.transit import get_transit_index


ROOT = Path(__file__).resolve().parents[1]


def payload(**overrides):
    row = {
        "original_plan": "Dinner",
        "failed_place": "",
        "failure_reason": "",
        "goal": "meal",
        "city": "Warsaw",
        "date": "2026-10-04",
        "start_time": "18:30",
        "return_by": "22:00",
        "min_stay_minutes": 75,
        "people": 2,
        "budget_total": 250,
        "currency": "PLN",
        "origin": "Warszawa Centralna",
        "travel_mode": "transit",
        "max_one_way_minutes": 30,
        "categories": ["restaurant"],
        "taste_refs": ["Amelie", "Radiohead"],
        "meal_required": True,
        "negotiable_extra_travel_minutes": 10,
        "negotiable_stay_reduction_minutes": 15,
        "allow_category_change": False,
    }
    row.update(overrides)
    return row


class RecordingProvider:
    mode = "recording"

    def __init__(self):
        self.pool_sizes = []

    def rank(self, places, taste_refs):
        self.pool_sizes.append(len(places))
        return [TasteResult(place.id, 0.5, index + 1, (), "recording") for index, place in enumerate(places)]


class WarsawPilotDataTests(unittest.TestCase):
    def test_street_index_is_large_and_suggests_locally(self):
        self.assertGreaterEqual(street_index.count, 5000)
        suggestions = street_index.suggest("Marsza", limit=12)
        self.assertTrue(any("Marszałkowska" in value for value in suggestions))

    def test_exact_address_index_is_large_and_resolves_without_network(self):
        self.assertGreaterEqual(address_index.count, 100000)
        result = geocoder.geocode("Chmielna 26")
        self.assertTrue(result.get("local_index"))
        self.assertAlmostEqual(float(result["lat"]), 52.23218, places=4)
        self.assertAlmostEqual(float(result["lon"]), 21.01334, places=4)

    def test_catalog_tracks_complete_recorded_osm_restaurant_snapshot(self):
        payload = json.loads((ROOT / "data" / "places_warsaw.json").read_text(encoding="utf-8"))
        rows = payload["places"]
        restaurants = [row for row in rows if row.get("category") == "restaurant"]
        imported = [row for row in restaurants if str(row.get("id", "")).startswith("warsaw:osm:")]
        meta = payload["catalog"]
        self.assertGreaterEqual(len(restaurants), 1500)
        self.assertGreaterEqual(int(meta["osm_restaurant_feature_count"]), 1500)
        self.assertEqual(int(meta["osm_restaurant_imported_count"]), len(imported))
        self.assertEqual(int(meta["curated_restaurant_count"]), 5)
        self.assertEqual(meta["osm_restaurant_snapshot"], "2026-10-04")
        self.assertTrue(all((row.get("price") or {}).get("status") == "unknown" for row in imported))

    def test_official_regular_hours_overlay_never_invents_meal_prices(self):
        engine = build_engine("baseline", "real")
        by_id = {place.id: place for place in engine.places}
        official = json.loads((ROOT / "data" / "restaurant_official_hours_20261014.json").read_text(encoding="utf-8"))
        self.assertEqual(official["checked_at"], "2026-10-14")
        self.assertGreaterEqual(len(official["entries"]), 12)
        for entry in official["entries"]:
            place = by_id[entry["id"]]
            self.assertEqual(place.name, entry["expected_name"])
            self.assertEqual(place.address, entry["expected_address"])
            self.assertEqual(place.hours_status, "confirmed")
            self.assertEqual(place.hours_source_url, entry["source_url"])
            self.assertEqual(place.hours_checked_at, "2026-10-14")
            self.assertEqual(set(place.hours), {str(day) for day in range(7)})
            if entry.get("price"):
                self.assertEqual(place.price.status, "confirmed")
                self.assertEqual(place.price.minimum, 49.0)
                self.assertEqual(place.price.maximum, 49.0)
                self.assertIn("Bigoli carbonara", place.price.basis)
                self.assertEqual(place.price.source_url, entry["price"]["source_url"])
                self.assertEqual(place.price.checked_at, "2026-10-14")
            else:
                self.assertEqual(place.price.status, "unknown")
                self.assertIsNone(place.price.minimum)
                self.assertIsNone(place.price.maximum)
            self.assertIn("Holiday exceptions", place.source_note)

        # This restaurant's Monday opening was updated from 12:00 in OSM to
        # 13:00 on the official autumn 2026 venue schedule.
        self.assertEqual(by_id["warsaw:osm:node:2859884304"].hours["0"], (("13:00", "23:00"),))
        self.assertEqual(by_id["warsaw:osm:node:4730432126"].hours["6"], ())
        self.assertEqual(by_id["warsaw:osm:node:314590527"].hours["0"], (("09:00", "00:00"),))
        self.assertEqual(by_id["warsaw:osm:node:6848092585"].price.minimum, 49)
        self.assertEqual(by_id["warsaw:osm:node:8663446811"].price.minimum, 49)
        self.assertEqual(by_id["warsaw:osm:way:400071446"].hours["0"], (("12:00", "23:30"),))
        self.assertEqual(by_id["warsaw:osm:node:338486362"].hours["6"], (("09:00", "00:00"),))
        from unstuck.planner import DayPlanner
        overnight = DayPlanner._windows(
            {"kind": "restaurant", "hours": {"0": [["09:00", "00:00"]]},
             "date_exceptions": {}, "hours_status": "confirmed"},
            date(2026, 10, 12),
        )
        self.assertEqual(overnight[0][1].date(), date(2026, 10, 13))
        # A curated venue with independently verified food prices keeps them.
        self.assertEqual(by_id["warsaw:hoza-steakhouse"].price.status, "confirmed")

    def test_exact_origin_coordinates_bypass_saved_origin_lookup(self):
        brief = SearchBrief.from_payload(
            payload(origin="Marszałkowska 10, Warszawa", origin_lat=52.225, origin_lon=21.015)
        )
        engine = build_engine("fixture", "real")
        result = engine.search(SearchState(brief))
        self.assertIn("cards", result)
        self.assertEqual(result["brief"]["origin_lat"], 52.225)
        self.assertEqual(result["brief"]["origin_lon"], 21.015)

    def test_fixture_or_baseline_can_rank_full_feasible_pool(self):
        engine = build_engine("baseline", "real")
        provider = RecordingProvider()
        engine.taste_provider = provider
        brief = SearchBrief.from_payload(
            payload(
                budget_total=500,
                max_one_way_minutes=60,
                negotiable_extra_travel_minutes=0,
                origin_lat=52.2297,
                origin_lon=21.0122,
            )
        )
        engine.search(SearchState(brief))
        self.assertTrue(provider.pool_sizes)
        self.assertGreater(max(provider.pool_sizes), 28)

    def test_live_mode_keeps_qloo_window_at_ten(self):
        class RecordingLiveProvider:
            mode = "live"

            def __init__(self):
                self.pool_sizes = []

            def rank(self, places, taste_refs):
                self.pool_sizes.append(len(places))
                return [
                    TasteResult(place.id, 1.0 - index * 0.01, index + 1, (), "qloo")
                    for index, place in enumerate(places)
                ]

        engine = build_engine("baseline", "real")
        provider = RecordingLiveProvider()
        engine.taste_provider = provider
        brief = SearchBrief.from_payload(
            payload(
                budget_total=500,
                max_one_way_minutes=60,
                negotiable_extra_travel_minutes=0,
                origin_lat=52.2297,
                origin_lon=21.0122,
            )
        )
        state = SearchState(brief)
        first = engine.search(state)
        self.assertLessEqual(max(provider.pool_sizes), 10)
        for card in first["cards"]:
            state.reject(card["id"])
        second = engine.search(state)
        self.assertTrue(second["cards"])
        self.assertLessEqual(max(provider.pool_sizes), 10)

    def test_transit_index_returns_real_scheduled_legs_and_geometry(self):
        router = get_transit_index()
        route = router.route(
            origin=(52.2289, 21.0034),
            destination=(52.2550, 21.0350),
            service_date=date(2026, 10, 4),
            departure_time="18:30",
        )
        self.assertIsNotNone(route)
        self.assertTrue(route["scheduled"])
        self.assertFalse(route["realtime"])
        transit_legs = [leg for leg in route["legs"] if leg["type"] == "transit"]
        self.assertTrue(transit_legs)
        self.assertTrue(all(leg["departure"] and leg["arrival"] for leg in transit_legs))
        self.assertTrue(all(len(leg["geometry"]) >= 2 for leg in transit_legs))
        self.assertGreater(route["duration_minutes"], 0)
        self.assertFalse(
            any(
                leg["type"] == "walk" and leg.get("from") == leg.get("to")
                for leg in route["legs"]
            ),
            "same-stop interchanges should render as transfers, not fake zero-distance walks",
        )


if __name__ == "__main__":
    unittest.main()
