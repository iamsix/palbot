#!/usr/bin/env python3
"""
Tests for modules.worldcup pure helpers.

These tests are intentionally network-free; they exercise the helpers that
the cog uses to parse API-Football payloads and render Discord-friendly
output. They follow the red→green discipline: this file lands first
without modules/worldcup.py, then the implementation lands to make it
pass.
"""
import json
import os
import sys
import unittest

# Make the repo root importable so `import modules.worldcup` works.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules import worldcup as wc  # noqa: E402


# ---------------------------------------------------------------------------
# Canned API payloads (trimmed to only the fields the parser touches).
# ---------------------------------------------------------------------------

FIXTURE_SCHEDULED = {
    "fixture": {
        "id": 1,
        "date": "2026-06-12T20:00:00+00:00",
        "status": {"short": "NS", "long": "Not Started", "elapsed": None},
        "venue": {"name": "MetLife Stadium"},
    },
    "teams": {
        "home": {"name": "USA"},
        "away": {"name": "Mexico"},
    },
    "goals": {"home": None, "away": None},
}

FIXTURE_LIVE_BIG_SCORE = {
    "fixture": {
        "id": 2,
        "date": "2026-06-15T18:00:00+00:00",
        "status": {"short": "2H", "long": "Second Half", "elapsed": 71},
        "venue": {"name": "SoFi Stadium"},
    },
    "teams": {
        "home": {"name": "Germany"},
        "away": {"name": "Brazil"},
    },
    "goals": {"home": 10, "away": 1},
}

FIXTURE_FINISHED_AET = {
    "fixture": {
        "id": 3,
        "date": "2026-07-01T22:00:00+00:00",
        "status": {"short": "AET", "long": "After Extra Time", "elapsed": 120},
        "venue": {"name": "BMO Field"},
    },
    "teams": {
        "home": {"name": "France"},
        "away": {"name": "Argentina"},
    },
    "goals": {"home": 3, "away": 2},
}

FIXTURE_FINISHED_PEN = {
    "fixture": {
        "id": 4,
        "date": "2026-07-05T22:00:00+00:00",
        "status": {"short": "PEN", "long": "Penalty Shootout", "elapsed": 120},
        "venue": {"name": "AT&T Stadium"},
    },
    "teams": {
        "home": {"name": "Spain"},
        "away": {"name": "Italy"},
    },
    "goals": {"home": 1, "away": 1},
}

FIXTURE_CANCELLED = {
    "fixture": {
        "id": 5,
        "date": "2026-06-20T20:00:00+00:00",
        "status": {"short": "CANC", "long": "Match Cancelled", "elapsed": None},
        "venue": {"name": "Estadio Azteca"},
    },
    "teams": {
        "home": {"name": "Japan"},
        "away": {"name": "Korea"},
    },
    "goals": {"home": None, "away": None},
}

FIXTURE_MALFORMED = {
    "fixture": {"id": 6},  # missing status/date/teams/goals
}


STANDINGS_PAYLOAD = {
    "response": [
        {
            "league": {
                "standings": [
                    [
                        {
                            "team": {"name": "USA"},
                            "group": "Group A",
                            "all": {
                                "played": 3, "win": 2, "draw": 1, "lose": 0,
                                "goals": {"for": 7, "against": 2},
                            },
                            "points": 7,
                        },
                        {
                            "team": {"name": "Mexico"},
                            "group": "Group A",
                            "all": {
                                "played": 3, "win": 1, "draw": 1, "lose": 1,
                                "goals": {"for": 4, "against": 4},
                            },
                            "points": 4,
                        },
                    ]
                ]
            }
        }
    ]
}

FIXTURES_PAYLOAD = {"response": [FIXTURE_SCHEDULED, FIXTURE_FINISHED_AET]}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class ParseFixtureStatusTests(unittest.TestCase):
    def test_scheduled_codes(self):
        for code in ("TBD", "NS"):
            self.assertEqual(wc._parse_fixture_status(code), "scheduled")

    def test_live_codes(self):
        for code in ("1H", "2H", "HT", "ET", "P", "LIVE", "BT", "INT"):
            self.assertEqual(wc._parse_fixture_status(code), "live")

    def test_finished_codes(self):
        for code in ("FT", "AET", "PEN"):
            self.assertEqual(wc._parse_fixture_status(code), "finished")

    def test_cancelled_codes(self):
        for code in ("CANC", "ABD", "AWD", "WO", "SUSP", "PST"):
            self.assertEqual(wc._parse_fixture_status(code), "cancelled")

    def test_unknown_code(self):
        self.assertEqual(wc._parse_fixture_status("ZZ"), "unknown")
        self.assertEqual(wc._parse_fixture_status(""), "unknown")
        self.assertEqual(wc._parse_fixture_status(None), "unknown")


class SafeHelpersTests(unittest.TestCase):
    def test_safe_score_none(self):
        self.assertEqual(wc._safe_score(None), "-")

    def test_safe_score_string(self):
        self.assertEqual(wc._safe_score("3"), "3")

    def test_safe_score_int(self):
        self.assertEqual(wc._safe_score(7), "7")

    def test_safe_int_none(self):
        self.assertEqual(wc._safe_int(None), 0)

    def test_safe_int_bad(self):
        self.assertEqual(wc._safe_int("abc"), 0)

    def test_safe_int_good(self):
        self.assertEqual(wc._safe_int("12"), 12)
        self.assertEqual(wc._safe_int(5), 5)


class BuildMatchDictTests(unittest.TestCase):
    def test_scheduled(self):
        m = wc._build_match_dict(FIXTURE_SCHEDULED)
        self.assertIsNotNone(m)
        self.assertTrue(m["scheduled"])
        self.assertEqual(m["ateam"], "Mexico")
        self.assertEqual(m["hteam"], "USA")
        # Scheduled rows should still expose dash-renderable scores
        self.assertEqual(m["ascore"], "-")
        self.assertEqual(m["hscore"], "-")
        # status should embed a Discord timestamp
        self.assertIn("<t:", m["status"])
        self.assertEqual(m["state"], "scheduled")

    def test_live_multi_digit(self):
        m = wc._build_match_dict(FIXTURE_LIVE_BIG_SCORE)
        self.assertIsNotNone(m)
        self.assertFalse(m["scheduled"])
        self.assertEqual(m["state"], "live")
        self.assertEqual(m["ascore"], "1")
        self.assertEqual(m["hscore"], "10")
        # minute should appear somewhere in status
        self.assertIn("71", m["status"])

    def test_finished_aet(self):
        m = wc._build_match_dict(FIXTURE_FINISHED_AET)
        self.assertIsNotNone(m)
        self.assertEqual(m["state"], "finished")
        self.assertFalse(m["scheduled"])
        self.assertIn("AET", m["status"])

    def test_finished_pen(self):
        m = wc._build_match_dict(FIXTURE_FINISHED_PEN)
        self.assertIsNotNone(m)
        self.assertEqual(m["state"], "finished")
        self.assertIn("Pen", m["status"])

    def test_cancelled(self):
        m = wc._build_match_dict(FIXTURE_CANCELLED)
        self.assertIsNotNone(m)
        self.assertEqual(m["state"], "cancelled")
        self.assertTrue(m["scheduled"])  # rendered like a no-score row

    def test_malformed_returns_none(self):
        self.assertIsNone(wc._build_match_dict(FIXTURE_MALFORMED))
        self.assertIsNone(wc._build_match_dict({}))
        self.assertIsNone(wc._build_match_dict(None))


class FormatMatchRowsTests(unittest.TestCase):
    def test_mixed_scheduled_and_finished_alignment(self):
        # 10-1 score forces slen=2 so scheduled rows must reserve 2-wide columns too.
        sched = wc._build_match_dict(FIXTURE_SCHEDULED)
        big = wc._build_match_dict(FIXTURE_LIVE_BIG_SCORE)
        rows = wc._format_match_rows([sched, big])
        self.assertEqual(len(rows), 2)
        for row in rows:
            # All rows wrapped in monospace backticks.
            self.assertTrue(row.startswith("`"))
            self.assertTrue(row.endswith("`"))
        # Lengths of the inner monospace content must match (proper alignment).
        inner_lengths = {len(r.strip("`").split(" | ")[0]) for r in rows}
        self.assertEqual(
            len(inner_lengths), 1,
            f"score columns should align across all rows, got widths {inner_lengths}",
        )

    def test_empty_input(self):
        self.assertEqual(wc._format_match_rows([]), [])


class GroupValidationTests(unittest.TestCase):
    def test_valid_groups(self):
        for g in "ABCDEFGHIJKL":
            self.assertEqual(wc._normalize_group(g), g)
            self.assertEqual(wc._normalize_group(g.lower()), g)

    def test_invalid_groups(self):
        for g in ("M", "Z", "AA", "", " ", None, "1"):
            self.assertIsNone(wc._normalize_group(g))


class PayloadEndToEndTests(unittest.TestCase):
    def test_parse_fixtures_payload(self):
        matches = [
            wc._build_match_dict(m) for m in FIXTURES_PAYLOAD["response"]
        ]
        matches = [m for m in matches if m is not None]
        self.assertEqual(len(matches), 2)
        rows = wc._format_match_rows(matches)
        self.assertEqual(len(rows), 2)

    def test_parse_standings_payload(self):
        groups = wc._extract_standings(STANDINGS_PAYLOAD)
        self.assertEqual(len(groups), 1)
        first = groups[0]
        self.assertEqual(first["name"], "Group A")
        self.assertEqual(len(first["rows"]), 2)
        usa = first["rows"][0]
        self.assertEqual(usa["team"], "USA")
        self.assertEqual(usa["pts"], 7)
        self.assertEqual(usa["gd"], 5)

    def test_extract_standings_empty(self):
        self.assertEqual(wc._extract_standings({}), [])
        self.assertEqual(wc._extract_standings({"response": []}), [])


if __name__ == "__main__":
    unittest.main()
