import copy
import json
import unittest
from pathlib import Path

from unstuck.models import Place
from unstuck.providers import QLOO_MAX_RANK_OPTIONS, RealQlooProvider


ROOT = Path(__file__).resolve().parents[1]


class QlooHarnessAlignmentTests(unittest.TestCase):
    def test_live_rank_uses_one_official_size_shortlist(self):
        class FakeTransport:
            def __init__(self):
                self.calls = []

            def get_json(self, path, params=None):
                params = params or {}
                self.calls.append((path, params))
                if path == "/search":
                    query = params["query"]
                    return {
                        "results": [
                            {
                                "entity_id": f"interest:{query}",
                                "name": query,
                                "types": ["urn:entity:movie"],
                            }
                        ]
                    }
                ids = params["filter.results.entities"].split(",")
                return {
                    "results": {
                        "entities": [
                            {
                                "entity_id": entity_id,
                                "name": entity_id,
                                "query": {"affinity": 1.0 - index / 100},
                            }
                            for index, entity_id in enumerate(ids)
                        ]
                    }
                }

        template = json.loads((ROOT / "data" / "places_fixture.json").read_text(encoding="utf-8"))["places"][0]
        places = []
        for index in range(QLOO_MAX_RANK_OPTIONS + 2):
            row = copy.deepcopy(template)
            row["id"] = f"fixture:qloo-{index}"
            row["name"] = f"Qloo Candidate {index}"
            row["qloo_entity_id"] = f"qloo:place:{index}"
            places.append(Place.from_dict(row))

        fake = FakeTransport()
        ranked = RealQlooProvider(fake).rank(places, ["Blade Runner"])
        insights = [params for path, params in fake.calls if path == "/v2/insights"]

        self.assertEqual(QLOO_MAX_RANK_OPTIONS, 10)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["take"], QLOO_MAX_RANK_OPTIONS)
        self.assertEqual(
            len(insights[0]["filter.results.entities"].split(",")),
            QLOO_MAX_RANK_OPTIONS,
        )
        self.assertEqual(len(ranked), len(places))
        self.assertTrue(all(row.rank is not None for row in ranked[:QLOO_MAX_RANK_OPTIONS]))
        self.assertTrue(all(row.rank is None for row in ranked[QLOO_MAX_RANK_OPTIONS:]))


if __name__ == "__main__":
    unittest.main()
