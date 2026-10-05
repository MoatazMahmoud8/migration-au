import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from processing_times_scraper import normalize_items


def assert_snapshot_contract(test_case: unittest.TestCase, snapshot: dict) -> None:
    test_case.assertEqual(snapshot.get("schemaVersion"), 2)
    test_case.assertIsInstance(snapshot.get("snapshotDate"), str)
    test_case.assertTrue(snapshot.get("items"))

    seen_subclasses = set()
    for item in snapshot["items"]:
        subclass = item.get("subclass")
        test_case.assertIsInstance(subclass, str)
        test_case.assertNotIn(subclass, seen_subclasses)
        seen_subclasses.add(subclass)

        test_case.assertNotIn("p50", item)
        test_case.assertNotIn("p90", item)
        test_case.assertNotIn("stream", item)
        test_case.assertTrue(item.get("streams"))

        seen_streams = set()
        for stream in item["streams"]:
            stream_name = stream.get("name", "")
            test_case.assertNotIn(stream_name, seen_streams)
            seen_streams.add(stream_name)
            test_case.assertIsInstance(stream.get("p50"), str)
            test_case.assertTrue(stream["p50"].strip())
            test_case.assertIsInstance(stream.get("p90"), str)
            test_case.assertTrue(stream["p90"].strip())


class ProcessingTimesContractTests(unittest.TestCase):
    def test_groups_legacy_rows_by_subclass_and_stream(self):
        rows = [
            {
                "subclass": "189",
                "name": "Skilled Independent",
                "category": "Skilled",
                "stream": "Points-tested stream",
                "p50": "9 months",
                "p90": "17 months",
                "icon": "globe-outline",
                "color": "#00C2FF",
                "url": "https://example.com/189",
            },
            {
                "subclass": "189",
                "name": "Skilled Independent",
                "category": "Skilled",
                "stream": "New Zealand stream",
                "p50": "4 months",
                "p90": "8 months",
                "icon": "globe-outline",
                "color": "#00C2FF",
                "url": "https://example.com/189",
            },
        ]

        result = normalize_items(rows)

        self.assertEqual(len(result), 1)
        self.assertEqual(
            [stream["name"] for stream in result[0]["streams"]],
            ["Points-tested stream", "New Zealand stream"],
        )
        self.assertTrue(all(key not in result[0] for key in ("p50", "p90", "stream")))

    def test_drops_malformed_and_duplicate_streams(self):
        rows = [
            {"subclass": "500", "p50": "29 days", "p90": "42 days"},
            {"subclass": "500", "p50": "30 days", "p90": "43 days"},
            {"subclass": "590", "p50": "", "p90": "60 days"},
        ]

        result = normalize_items(rows)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["subclass"], "500")
        self.assertEqual(result[0]["streams"], [{"p50": "29 days", "p90": "42 days"}])

    def test_checked_in_snapshot_matches_v2_contract(self):
        snapshot = json.loads((ROOT / "public" / "processing-times.json").read_text(encoding="utf-8"))
        assert_snapshot_contract(self, snapshot)


if __name__ == "__main__":
    unittest.main()
