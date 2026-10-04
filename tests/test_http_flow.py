from __future__ import annotations

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

from app import AppState, Handler, build_engine


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
        health = self.get_json("/api/health")
        self.assertTrue(health["ok"])
        self.assertEqual(health["catalog_mode"], "real")
        self.assertEqual(health["provider_mode"], "fixture")

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
        self.assertEqual(first["result_status"], "confirmed")
        self.assertTrue(first["cards"])
        rejected_id = first["cards"][0]["id"]

        second = self.post_json(
            "/api/reject", {"session_id": first["session_id"], "place_id": rejected_id}
        )
        self.assertEqual(second["round"], 2)
        self.assertIn(rejected_id, second["rejected_ids"])
        self.assertNotIn(rejected_id, {card["id"] for card in second["cards"]})

        third = self.post_json(
            "/api/update",
            {"session_id": first["session_id"], "patch": {"budget_total": 220}},
        )
        self.assertEqual(third["round"], 3)
        self.assertIn(rejected_id, third["rejected_ids"])
        self.assertNotIn(rejected_id, {card["id"] for card in third["cards"]})


if __name__ == "__main__":
    unittest.main()
