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

    def test_catalog_has_hundreds_of_restaurants(self):
        rows = json.loads((ROOT / "data" / "places_warsaw.json").read_text(encoding="utf-8"))["places"]
        restaurants = [row for row in rows if row.get("category") == "restaurant"]
        self.assertGreaterEqual(len(restaurants), 400)
        imported = [row for row in restaurants if str(row.get("id", "")).startswith("warsaw:osm:")]
        self.assertGreaterEqual(len(imported), 390)
        self.assertTrue(all((row.get("price") or {}).get("status") == "unknown" for row in imported))

    def test_exact_origin_coordinates_bypass_saved_origin_lookup(self):
        brief = SearchBrief.from_payload(
            payload(origin="Marszałkowska 10, Warszawa", origin_lat=52.225, origin_lon=21.015)
        )
        engine = build_engine("fixture", "real")
        result = engine.search(SearchState(brief))
        self.assertIn("cards", result)
        self.assertEqual(result["brief"]["origin_lat"], 52.225)
        self.assertEqual(result["brief"]["origin_lon"], 21.015)

    def test_large_catalog_is_prefiltered_before_taste_provider(self):
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
        self.assertLessEqual(max(provider.pool_sizes), 28)

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
