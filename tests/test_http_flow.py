from __future__ import annotations

import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from unittest.mock import patch

from app import AppState, Handler, build_engine, google_place_media
from unstuck.geocoding import address_index


class FakeJsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _limit=-1):
        return json.dumps(self.payload).encode("utf-8")


class HttpFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Handler.app_state = AppState(build_engine("fixture", "real"))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get_json(self, path):
        with urlopen(self.base + path, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))

    def post_json(self, path, payload):
        request = Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_search_reject_update_end_to_end(self):
        version = self.get_json("/api/version")
        self.assertEqual(version["git_repo"], os.environ.get("RENDER_GIT_REPO_SLUG", "MeowRona/Unstuck"))
        self.assertIn("git_commit", version)

        health = self.get_json("/api/health")
        self.assertTrue(health["ok"])
        self.assertEqual(health["catalog_mode"], "real")
        self.assertEqual(health["provider_mode"], "fixture")
        self.assertEqual(health["google_places_api_key_present"], bool(os.environ.get("GOOGLE_PLACES_API_KEY")))
        self.assertFalse(health["google_places_enabled"])
        self.assertGreaterEqual(health["street_count"], 5000)
        self.assertTrue(health["transit_index_present"])

        streets = self.get_json("/api/streets?q=Marsza")
        self.assertTrue(any("Marsza" in row for row in streets["suggestions"]))

        sample = next(row for row in address_index.rows.values() if isinstance(row, list) and len(row) >= 4)
        reversed_address = self.post_json(
            "/api/reverse-geocode",
            {"lat": sample[2], "lon": sample[3]},
        )
        self.assertTrue(reversed_address["available"])
        self.assertIn(str(sample[0]), reversed_address["label"])
        self.assertLessEqual(reversed_address["distance_m"], 1)

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
            "budget_total": 200,
            "currency": "PLN",
            "origin": "Warsaw Central",
            "travel_mode": "transit",
            "max_one_way_minutes": 25,
            "categories": ["restaurant"],
            "taste_refs": ["Amelie", "Radiohead"],
            "meal_required": True,
            "negotiable_extra_travel_minutes": 8,
            "negotiable_stay_reduction_minutes": 15,
            "allow_category_change": False,
        }
        first = self.post_json("/api/search", payload)
        self.assertEqual(first["round"], 1)
        self.assertIn(first["result_status"], {"requires_checking", "mixed", "confirmed"})
        self.assertTrue(first["cards"])
        self.assertTrue(
            any(
                check["field"] == "one-way travel" and check["status"] == "unknown"
                for check in first["cards"][0]["constraint_checks"]
            )
        )
        rejected_id = first["cards"][0]["id"]

        second = self.post_json(
            "/api/reject",
            {"session_id": first["session_id"], "place_id": rejected_id, "reason": "not_my_vibe"},
        )
        self.assertEqual(second["round"], 2)
        self.assertIn(rejected_id, second["rejected_ids"])
        self.assertEqual(second["rejection_history"][-1]["reason"], "not_my_vibe")
        self.assertNotIn(rejected_id, {card["id"] for card in second["cards"]})

        restored = self.post_json(
            "/api/undo-reject",
            {"session_id": first["session_id"]},
        )
        self.assertEqual(restored["restored_rejection"]["place_id"], rejected_id)
        self.assertNotIn(rejected_id, restored["rejected_ids"])

        third = self.post_json(
            "/api/update",
            {"session_id": first["session_id"], "patch": {"budget_total": 220}},
        )
        self.assertEqual(third["round"], 4)
        self.assertNotIn(rejected_id, third["rejected_ids"])

    def test_route_check_recalculates_outbound_and_return(self):
        payload = {
            "original_plan": "Dinner",
            "failed_place": "",
            "failure_reason": "",
            "goal": "meal",
            "city": "Warsaw",
            "date": "2026-10-10",
            "start_time": "18:30",
            "return_by": "23:00",
            "min_stay_minutes": 60,
            "people": 2,
            "budget_total": 500,
            "currency": "PLN",
            "origin": "Warsaw Central",
            "travel_mode": "transit",
            "max_one_way_minutes": 25,
            "categories": ["restaurant"],
            "taste_refs": ["Amelie"],
            "meal_required": True,
            "negotiable_extra_travel_minutes": 10,
            "negotiable_stay_reduction_minutes": 0,
            "allow_category_change": False,
        }
        first = self.post_json("/api/search", payload)
        place_id = first["cards"][0]["id"]

        outbound = {
            "mode": "transit",
            "scheduled": True,
            "realtime": False,
            "departure": "18:30",
            "arrival": "18:58",
            "duration_minutes": 28,
            "transfers": 0,
            "summary": "10",
            "legs": [],
            "source": {"name": "Warsaw GTFS schedule", "url": "https://example.test/gtfs"},
        }
        inbound = {
            "mode": "transit",
            "scheduled": True,
            "realtime": False,
            "departure": "19:58",
            "arrival": "20:28",
            "duration_minutes": 30,
            "transfers": 0,
            "summary": "10",
            "legs": [],
            "source": {"name": "Warsaw GTFS schedule", "url": "https://example.test/gtfs"},
        }
        with patch("app.route_transit", side_effect=[outbound, inbound]):
            checked = self.post_json(
                "/api/route-check",
                {"session_id": first["session_id"], "place_id": place_id},
            )

        self.assertEqual(checked["checked_place_id"], place_id)
        self.assertEqual(checked["route"]["duration_minutes"], 28)
        self.assertEqual(checked["return_route"]["duration_minutes"], 30)
        matching = [card for card in checked["cards"] if card["id"] == place_id]
        if matching:
            card = matching[0]
            self.assertFalse(card["timing"]["travel_is_estimate"])
            self.assertEqual(card["timing"]["travel_one_way_minutes"], 28)
            self.assertEqual(card["timing"]["travel_return_minutes"], 30)
            fields = {change["field"] for change in card["change"]}
            self.assertIn("one-way travel", fields)

    def test_google_place_media_is_disabled_by_default_even_with_key(self):
        place_id = "ChIJM-LLX_HMHkcRPDiwF3WzN4Q"
        with patch.dict(
            os.environ,
            {"GOOGLE_PLACES_API_KEY": "reserved-for-jury", "GOOGLE_PLACES_ENABLED": "false"},
        ), patch("app.urlopen") as mocked_urlopen:
            payload = google_place_media(place_id, {place_id})
        self.assertFalse(payload["available"])
        self.assertEqual(payload["reason"], "GOOGLE_PLACES_DISABLED")
        mocked_urlopen.assert_not_called()

    def test_google_place_media_enabled_without_key_is_honest(self):
        place_id = "ChIJM-LLX_HMHkcRPDiwF3WzN4Q"
        with patch.dict(
            os.environ,
            {"GOOGLE_PLACES_API_KEY": "", "GOOGLE_PLACES_ENABLED": "true"},
        ):
            payload = google_place_media(place_id, {place_id})
        self.assertFalse(payload["available"])
        self.assertIn("GOOGLE_PLACES_API_KEY", payload["reason"])
        self.assertTrue(payload["google_maps_uri"].startswith("https://www.google.com/maps/"))

    def test_google_place_media_parses_live_fields_without_persisting(self):
        place_id = "ChIJM-LLX_HMHkcRPDiwF3WzN4Q"
        details = {
            "rating": 4.6,
            "userRatingCount": 3672,
            "googleMapsUri": "https://maps.google.com/example",
            "photos": [
                {
                    "name": f"places/{place_id}/photos/test-photo",
                    "authorAttributions": [
                        {"displayName": "Example Author", "uri": "https://example.com/author"}
                    ],
                }
            ],
        }
        media = {"photoUri": "https://lh3.googleusercontent.com/example-photo"}
        with patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "test-key", "GOOGLE_PLACES_ENABLED": "true"}), patch(
            "app.urlopen",
            side_effect=[FakeJsonResponse(details), FakeJsonResponse(media)],
        ):
            payload = google_place_media(place_id, {place_id})

        self.assertTrue(payload["available"])
        self.assertEqual(payload["rating"], 4.6)
        self.assertEqual(payload["user_rating_count"], 3672)
        self.assertEqual(payload["photo"]["uri"], media["photoUri"])
        self.assertEqual(
            payload["photo"]["author_attributions"][0]["displayName"],
            "Example Author",
        )


if __name__ == "__main__":
    unittest.main()
