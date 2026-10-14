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
        self.assertEqual(len(official["entries"]), 32)
        self.assertEqual(len({item["id"] for item in official["entries"]}), 32)
        for entry in official["entries"]:
            place = by_id[entry["id"]]
            self.assertEqual(place.name, entry["expected_name"])
            self.assertEqual(place.address, entry["expected_address"])
            self.assertEqual(place.hours_status, entry.get("hours_status", "confirmed"))
            self.assertEqual(place.hours_source_url, entry["source_url"])
            self.assertEqual(place.hours_checked_at, "2026-10-14")
            self.assertEqual(set(place.hours), {str(day) for day in range(7)})
            if entry.get("price"):
                self.assertEqual(place.price.status, "confirmed")
                self.assertEqual(place.price.minimum, float(entry["price"]["min"]))
                self.assertEqual(place.price.maximum, float(entry["price"]["max"]))
                self.assertEqual(place.price.basis, "per_person_dish_only")
                self.assertIn(entry["price"]["item_note"][:25], place.source_note)
                self.assertIn("not an all-inclusive meal", place.source_note)
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
        self.assertEqual(by_id["warsaw:osm:way:400071446"].price.minimum, 49)
        self.assertIn("minced-meat cutlets", by_id["warsaw:osm:way:400071446"].source_note)
        self.assertEqual(by_id["warsaw:osm:node:4004769301"].price.minimum, 69)
        self.assertIn("kopytka", by_id["warsaw:osm:node:4004769301"].source_note)
        self.assertIn("12.5-percent service", by_id["warsaw:osm:node:4004769301"].source_note)
        self.assertEqual(sum(bool(entry.get("price")) for entry in official["entries"]), 6)
        self.assertEqual(by_id["warsaw:osm:way:400071446"].hours["0"], (("12:00", "23:30"),))
        self.assertEqual(by_id["warsaw:osm:node:338486362"].hours["6"], (("09:00", "00:00"),))
        self.assertEqual(by_id["warsaw:osm:node:3621635056"].hours["0"], (("12:30", "21:30"),))
        self.assertEqual(by_id["warsaw:osm:node:6421840214"].hours["6"], (("12:30", "21:00"),))
        self.assertEqual(by_id["warsaw:osm:node:4004769301"].hours["6"], (("12:00", "20:00"),))
        self.assertEqual(by_id["warsaw:osm:node:447986173"].hours["0"], (("11:00", "23:00"),))
        self.assertEqual(by_id["warsaw:osm:node:6023094185"].hours["5"], (("12:00", "22:00"),))
        self.assertEqual(by_id["warsaw:osm:node:2640176381"].hours["0"], (("12:00", "20:00"),))
        self.assertEqual(by_id["warsaw:osm:node:416560107"].hours["6"], (("12:00", "22:00"),))
        self.assertEqual(by_id["warsaw:osm:node:4741653125"].hours["6"], (("12:00", "00:00"),))
        self.assertEqual(by_id["warsaw:osm:node:7705273908"].hours["4"], (("11:00", "00:00"),))
        self.assertEqual(sum(by_id[entry["id"]].hours_status == "confirmed"
                             for entry in official["entries"]), 30)
        self.assertEqual(sum(by_id[entry["id"]].hours_status == "estimated"
                             for entry in official["entries"]), 2)
        self.assertIn("conflicting operator", by_id["warsaw:osm:node:3621635056"].source_note)
        self.assertIn("conflicting operator", by_id["warsaw:osm:node:6421840214"].source_note)
        self.assertEqual(by_id["warsaw:osm:node:5073937636"].hours["4"], (("12:00", "23:00"),))
        self.assertEqual(by_id["warsaw:osm:node:4834770520"].hours["6"], (("13:00", "21:15"),))
        self.assertEqual(by_id["warsaw:osm:node:5062561421"].price.minimum, 42)
        self.assertIn("Falafel & hummus", by_id["warsaw:osm:node:5062561421"].source_note)
        self.assertIn("in-restaurant price may differ", by_id["warsaw:osm:node:5062561421"].source_note)
        self.assertEqual(by_id["warsaw:osm:node:1285589018"].price.minimum, 42)
        self.assertIn("vegetarian futomaki", by_id["warsaw:osm:node:1285589018"].source_note)

        # Nine additional exact branches verified against the operator's own
        # weekly schedule; a same-name branch without evidence stays untouched.
        expected_hours = {
            "warsaw:osm:node:1285589018": ("4", (("12:00", "23:00"),)),
            "warsaw:osm:node:5062561421": ("5", (("10:00", "00:00"),)),
            "warsaw:osm:node:4369986677": ("0", (("12:00", "22:00"),)),
            "warsaw:osm:node:11035383264": ("6", (("12:00", "22:00"),)),
            "warsaw:osm:node:9773126020": ("6", (("09:00", "23:00"),)),
            "warsaw:osm:node:4408894491": ("4", (("11:30", "23:00"),)),
            "warsaw:osm:node:9327944759": ("0", ()),
            "warsaw:osm:node:327614538": ("2", (("10:00", "00:00"),)),
            "warsaw:osm:node:3582751797": ("5", (("09:00", "23:00"),)),
        }
        for restaurant_id, (weekday, expected) in expected_hours.items():
            item = by_id[restaurant_id]
            self.assertEqual(item.hours_status, "confirmed", restaurant_id)
            self.assertEqual(item.hours[weekday], expected, restaurant_id)
            self.assertTrue(item.hours_source_url.startswith("https://"), restaurant_id)
            self.assertEqual(item.price.status, "unknown", restaurant_id)
        self.assertNotEqual(by_id["warsaw:osm:node:6898019913"].hours_status, "confirmed")
        self.assertNotEqual(by_id["warsaw:osm:node:4799316222"].hours_status, "confirmed")

        from unstuck.planner import DayPlanner
        overnight = DayPlanner._windows(
            {"kind": "restaurant", "hours": {"0": [["09:00", "00:00"]]},
             "date_exceptions": {}, "hours_status": "confirmed"},
            date(2026, 10, 12),
        )
        self.assertEqual(overnight[0][1].date(), date(2026, 10, 13))
        # A curated venue with independently verified food prices keeps them.
        self.assertEqual(by_id["warsaw:hoza-steakhouse"].price.status, "confirmed")

    def test_operator_announced_closed_restaurant_is_not_recommended(self):
        source = json.loads((ROOT / "data" / "restaurant_closures_20261014.json").read_text(encoding="utf-8"))
        self.assertEqual(source["checked_at"], "2026-10-14")
        entry = source["entries"][0]
        self.assertEqual(entry["status"], "operator_reports_closed")
        self.assertEqual(entry["source_url"], "https://www.alegloria.pl/")
        raw = json.loads((ROOT / "data" / "places_warsaw.json").read_text(encoding="utf-8"))
        self.assertTrue(any(row["id"] == entry["id"] for row in raw["places"]),
                        "the source OSM catalog still contains the outdated venue")
        engine = build_engine("baseline", "real")
        self.assertFalse(any(p.id == entry["id"] for p in engine.places))
        from unstuck.planner import PlannerCatalog
        catalog = PlannerCatalog(engine.places)
        self.assertNotIn("restaurant:" + entry["id"], {
            row["id"] for row in catalog.restaurant_rows
        })

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
