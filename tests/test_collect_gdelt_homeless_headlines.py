import gzip
import importlib.util
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "collect_gdelt_homeless_headlines.py"
SPEC = importlib.util.spec_from_file_location("collect_gdelt_homeless_headlines", SCRIPT)
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)


class GalCollectorTests(unittest.TestCase):
    def test_historical_file_url_uses_utc_minute_filename(self):
        url = collector.minute_url(
            collector.DEFAULT_BASE_URL, datetime(2024, 1, 1, 0, 1)
        )
        self.assertEqual(
            url,
            "https://storage.googleapis.com/data.gdeltproject.org/gdeltv3/gal/"
            "20240101000100.gal.json.gz",
        )

    def test_parser_filters_language_and_records_matching_terms(self):
        records = [
            {
                "date": "2024-01-01T00:00:00Z",
                "url": "https://example.com/a?utm_source=test&id=7",
                "domain": "example.com",
                "outletName": "Example News",
                "title": "City expands services for unhoused residents",
                "lang": "en",
            },
            {
                "url": "https://example.com/b",
                "title": "Homelessness headline in another language",
                "lang": "es",
            },
        ]
        payload = gzip.compress(
            "\n".join(json.dumps(record) for record in records).encode("utf-8")
        )
        patterns = collector.compile_headline_patterns(["homelessness", "unhoused"])
        matches, malformed = collector.parse_gal_payload(
            payload, patterns, True, "https://example.test/file.gz"
        )
        self.assertEqual(malformed, 0)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["matching_terms"], "unhoused")
        self.assertEqual(matches[0]["normalized_url"], "https://example.com/a?id=7")

    def test_phrase_matching_does_not_match_substrings(self):
        patterns = collector.compile_headline_patterns(
            ["homeless", "people experiencing homelessness"]
        )
        self.assertFalse(patterns[0][1].search("A homelessness report"))
        self.assertTrue(patterns[1][1].search("People experiencing homelessness need help"))

    def test_article_identifier_is_stable_after_tracking_cleanup(self):
        first = collector.normalize_url("https://example.com/story?utm_medium=email&id=2")
        second = collector.normalize_url("https://EXAMPLE.com/story?id=2#section")
        self.assertEqual(collector.article_id(first), collector.article_id(second))

    def test_empty_or_reversed_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            collector.compile_headline_patterns(["  "])
        args = collector.build_parser().parse_args(
            ["--start-date", "2024-02-01", "--end-date", "2024-01-01"]
        )
        with self.assertRaises(collector.CollectionError):
            collector.collect(args)


if __name__ == "__main__":
    unittest.main()
