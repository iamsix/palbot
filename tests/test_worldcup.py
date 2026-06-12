#!/usr/bin/env python3
"""
Tests for modules.worldcup pure helpers (ESPN backend).

The cog talks to ESPN's undocumented public scoreboard / standings
endpoints (no auth, no key). These tests are network-free and exercise
the helpers that parse those payloads.

Sample shapes were taken from live curl responses against
``site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard``
and ``/apis/v2/sports/soccer/fifa.world/standings``.
"""
import os
import sys
import unittest

# Make the repo root importable so `import modules.worldcup` works.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules import worldcup as wc  # noqa: E402


# ---------------------------------------------------------------------------
# Canned ESPN payloads (trimmed to only the fields the parser touches).
# ESPN scoreboard envelope is: {"events": [event, ...]}.
# Each event has `name`, `date`, `status.type.{name,state,detail,...}`
# and `competitions[0].competitors[]` (with `homeAway`, `score` (string!),
# `team.{displayName,abbreviation}`).
# ---------------------------------------------------------------------------


def _event(eid, name, iso_date, status_name, state, detail,
           home_team, away_team, home_score, away_score, venue="",
           home_winner=False, away_winner=False):
    return {
        "id": eid,
        "name": name,
        "date": iso_date,
        "status": {
            "type": {
                "name": status_name,
                "state": state,
                "detail": detail,
                "shortDetail": detail,
            },
        },
        "competitions": [
            {
                "venue": {"fullName": venue} if venue else {},
                "competitors": [
                    {
                        "homeAway": "home",
                        "score": home_score,
                        "winner": home_winner,
                        "team": {
                            "displayName": home_team,
                            "abbreviation": home_team[:3].upper(),
                        },
                    },
                    {
                        "homeAway": "away",
                        "score": away_score,
                        "winner": away_winner,
                        "team": {
                            "displayName": away_team,
                            "abbreviation": away_team[:3].upper(),
                        },
                    },
                ],
            }
        ],
    }


EVENT_SCHEDULED = _event(
    "1", "Mexico at USA", "2026-06-12T20:00Z",
    "STATUS_SCHEDULED", "pre", "Fri, June 12th at 8:00 PM EDT",
    "USA", "Mexico", None, None, venue="MetLife Stadium",
)

EVENT_LIVE_BIG_SCORE = _event(
    "2", "Brazil at Germany", "2026-06-15T18:00Z",
    "STATUS_IN_PROGRESS", "in", "71'",
    "Germany", "Brazil", "10", "1", venue="SoFi Stadium",
)

EVENT_HALFTIME = _event(
    "20", "Brazil at Germany", "2026-06-15T18:00Z",
    "STATUS_HALFTIME", "in", "HT",
    "Germany", "Brazil", "2", "0", venue="SoFi Stadium",
)

EVENT_FINISHED_FT = _event(
    "30", "South Africa at Mexico", "2026-06-11T19:00Z",
    "STATUS_FULL_TIME", "post", "FT",
    "Mexico", "South Africa", "2", "0",
    venue="Estadio Azteca", home_winner=True,
)

EVENT_FINISHED_FINAL = _event(
    "31", "Argentina at France", "2026-07-01T22:00Z",
    "STATUS_FINAL", "post", "FT",
    "France", "Argentina", "3", "2", venue="BMO Field", home_winner=True,
)

EVENT_CANCELLED = _event(
    "40", "Korea at Japan", "2026-06-20T20:00Z",
    "STATUS_CANCELED", "post", "Canceled",
    "Japan", "Korea", None, None, venue="Estadio Azteca",
)

EVENT_POSTPONED = _event(
    "41", "Italy at Spain", "2026-07-05T22:00Z",
    "STATUS_POSTPONED", "pre", "Postponed",
    "Spain", "Italy", None, None, venue="AT&T Stadium",
)

EVENT_MALFORMED = {"id": "x"}  # no competitions / status

SCOREBOARD_PAYLOAD = {"events": [EVENT_SCHEDULED, EVENT_FINISHED_FT]}


# ---------------------------------------------------------------------------
# ESPN standings envelope:
#   {"children": [
#       {"name": "Group A",
#        "standings": {"entries": [
#            {"team": {"displayName": "..."},
#             "stats": [{"name": "wins", "value": 1.0, "displayValue": "1"}, ...],
#            }, ...
#        ]}}
#   ]}
# ---------------------------------------------------------------------------


def _stat(name, value, display=None):
    return {"name": name, "value": value,
            "displayValue": display if display is not None else str(value)}


def _entry(team, gp, w, d, l_, gf, ga, gd, pts):
    return {
        "team": {"displayName": team, "abbreviation": team[:3].upper()},
        "stats": [
            _stat("gamesPlayed", gp),
            _stat("wins", w),
            _stat("ties", d),
            _stat("losses", l_),
            _stat("pointsFor", gf),
            _stat("pointsAgainst", ga),
            _stat("pointDifferential", gd,
                  display=f"+{gd}" if gd > 0 else str(gd)),
            _stat("points", pts),
        ],
    }


STANDINGS_PAYLOAD = {
    "children": [
        {
            "name": "Group A",
            "standings": {
                "entries": [
                    _entry("USA", 3, 2, 1, 0, 7, 2, 5, 7),
                    _entry("Mexico", 3, 1, 1, 1, 4, 4, 0, 4),
                ],
            },
        },
    ],
}

STANDINGS_PAYLOAD_TWO_GROUPS = {
    "children": [
        {
            "name": "Group A",
            "standings": {"entries": [
                _entry("USA", 3, 2, 1, 0, 7, 2, 5, 7),
                _entry("Mexico", 3, 1, 1, 1, 4, 4, 0, 4),
            ]},
        },
        {
            "name": "Group B",
            "standings": {"entries": [
                _entry("Germany", 3, 3, 0, 0, 9, 1, 8, 9),
                _entry("Brazil", 3, 2, 0, 1, 6, 3, 3, 6),
            ]},
        },
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class ParseFixtureStatusTests(unittest.TestCase):
    """ESPN exposes both a high-level state (pre/in/post) and a granular
    type name. The bucketer must collapse both into our four buckets."""

    def test_scheduled(self):
        self.assertEqual(
            wc._parse_fixture_status({"name": "STATUS_SCHEDULED", "state": "pre"}),
            "scheduled",
        )

    def test_live_in_progress(self):
        self.assertEqual(
            wc._parse_fixture_status({"name": "STATUS_IN_PROGRESS", "state": "in"}),
            "live",
        )

    def test_live_halftime(self):
        self.assertEqual(
            wc._parse_fixture_status({"name": "STATUS_HALFTIME", "state": "in"}),
            "live",
        )

    def test_finished_full_time(self):
        self.assertEqual(
            wc._parse_fixture_status({"name": "STATUS_FULL_TIME", "state": "post"}),
            "finished",
        )

    def test_finished_final(self):
        self.assertEqual(
            wc._parse_fixture_status({"name": "STATUS_FINAL", "state": "post"}),
            "finished",
        )

    def test_cancelled(self):
        self.assertEqual(
            wc._parse_fixture_status({"name": "STATUS_CANCELED", "state": "post"}),
            "cancelled",
        )

    def test_postponed(self):
        self.assertEqual(
            wc._parse_fixture_status({"name": "STATUS_POSTPONED", "state": "pre"}),
            "cancelled",
        )

    def test_unknown(self):
        self.assertEqual(
            wc._parse_fixture_status({"name": "STATUS_WAT", "state": "weird"}),
            "unknown",
        )
        self.assertEqual(wc._parse_fixture_status({}), "unknown")
        self.assertEqual(wc._parse_fixture_status(None), "unknown")


class SafeHelpersTests(unittest.TestCase):
    def test_safe_score_none(self):
        self.assertEqual(wc._safe_score(None), "-")

    def test_safe_score_zero_string(self):
        # ESPN returns scores as strings — "0" must stay "0", not collapse to "-".
        self.assertEqual(wc._safe_score("0"), "0")

    def test_safe_score_zero_int(self):
        self.assertEqual(wc._safe_score(0), "0")

    def test_safe_score_string(self):
        self.assertEqual(wc._safe_score("3"), "3")

    def test_safe_score_int(self):
        self.assertEqual(wc._safe_score(7), "7")

    def test_safe_int_none(self):
        self.assertEqual(wc._safe_int(None), 0)

    def test_safe_int_bad(self):
        self.assertEqual(wc._safe_int("abc"), 0)

    def test_safe_int_string(self):
        self.assertEqual(wc._safe_int("12"), 12)

    def test_safe_int_float(self):
        # ESPN returns standings stats as floats (`"value": 3.0`).
        self.assertEqual(wc._safe_int(3.0), 3)


class BuildMatchDictTests(unittest.TestCase):
    def test_scheduled(self):
        m = wc._build_match_dict(EVENT_SCHEDULED)
        self.assertIsNotNone(m)
        self.assertTrue(m["scheduled"])
        self.assertEqual(m["hteam"], "USA")
        self.assertEqual(m["ateam"], "Mexico")
        self.assertEqual(m["ascore"], "-")
        self.assertEqual(m["hscore"], "-")
        self.assertEqual(m["state"], "scheduled")
        # Status should embed a Discord timestamp for the kickoff.
        self.assertIn("<t:", m["status"])

    def test_live_multi_digit(self):
        m = wc._build_match_dict(EVENT_LIVE_BIG_SCORE)
        self.assertIsNotNone(m)
        self.assertFalse(m["scheduled"])
        self.assertEqual(m["state"], "live")
        self.assertEqual(m["hteam"], "Germany")
        self.assertEqual(m["ateam"], "Brazil")
        self.assertEqual(m["hscore"], "10")
        self.assertEqual(m["ascore"], "1")
        # ESPN's "71'" detail should appear in the status label.
        self.assertIn("71", m["status"])

    def test_halftime(self):
        m = wc._build_match_dict(EVENT_HALFTIME)
        self.assertIsNotNone(m)
        self.assertEqual(m["state"], "live")
        self.assertIn("HT", m["status"])

    def test_finished_full_time(self):
        m = wc._build_match_dict(EVENT_FINISHED_FT)
        self.assertIsNotNone(m)
        self.assertEqual(m["state"], "finished")
        self.assertFalse(m["scheduled"])
        self.assertEqual(m["hscore"], "2")
        self.assertEqual(m["ascore"], "0")
        self.assertIn("FT", m["status"])

    def test_finished_final(self):
        m = wc._build_match_dict(EVENT_FINISHED_FINAL)
        self.assertIsNotNone(m)
        self.assertEqual(m["state"], "finished")
        self.assertEqual(m["hscore"], "3")
        self.assertEqual(m["ascore"], "2")

    def test_cancelled(self):
        m = wc._build_match_dict(EVENT_CANCELLED)
        self.assertIsNotNone(m)
        self.assertEqual(m["state"], "cancelled")
        self.assertTrue(m["scheduled"])
        self.assertIn("Cancel", m["status"])

    def test_postponed_buckets_as_cancelled(self):
        m = wc._build_match_dict(EVENT_POSTPONED)
        self.assertIsNotNone(m)
        self.assertEqual(m["state"], "cancelled")
        self.assertIn("Postpon", m["status"])

    def test_malformed_returns_none(self):
        self.assertIsNone(wc._build_match_dict(EVENT_MALFORMED))
        self.assertIsNone(wc._build_match_dict({}))
        self.assertIsNone(wc._build_match_dict(None))


class FormatMatchRowsTests(unittest.TestCase):
    def test_mixed_scheduled_and_finished_alignment(self):
        # 10-1 score forces slen=2 so scheduled rows must reserve 2-wide columns.
        sched = wc._build_match_dict(EVENT_SCHEDULED)
        big = wc._build_match_dict(EVENT_LIVE_BIG_SCORE)
        rows = wc._format_match_rows([sched, big])
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertTrue(row.startswith("`"))
            self.assertTrue(row.endswith("`"))
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
    def test_parse_scoreboard_payload(self):
        matches = [wc._build_match_dict(e) for e in SCOREBOARD_PAYLOAD["events"]]
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
        self.assertEqual(usa["gf"], 7)
        self.assertEqual(usa["ga"], 2)

    def test_extract_standings_empty(self):
        self.assertEqual(wc._extract_standings({}), [])
        self.assertEqual(wc._extract_standings({"children": []}), [])


class MultiGroupStandingsTests(unittest.TestCase):
    """Regression guard: every group must be parsed, not just the first."""

    def test_parse_two_groups(self):
        groups = wc._extract_standings(STANDINGS_PAYLOAD_TWO_GROUPS)
        self.assertEqual(len(groups), 2)
        names = [g["name"] for g in groups]
        self.assertIn("Group A", names)
        self.assertIn("Group B", names)
        teams = {row["team"] for g in groups for row in g["rows"]}
        for expected in ("USA", "Mexico", "Germany", "Brazil"):
            self.assertIn(expected, teams)


class FormatStandingsTableTests(unittest.TestCase):
    """Regression guard: GD column must be signed and right-aligned."""

    def _row(self, team, gd, pts=0):
        return {
            "team": team, "mp": 3, "w": 0, "d": 0, "l": 0,
            "gf": max(gd, 0), "ga": max(-gd, 0), "gd": gd, "pts": pts,
        }

    def test_signed_right_aligned_gd_column(self):
        rendered = wc._format_standings_table(
            [self._row("USA", 5, pts=9), self._row("Mexico", -3, pts=0)]
        )
        self.assertIn("  +5", rendered)
        self.assertIn("  -3", rendered)

    def test_zero_gd_still_signed(self):
        rendered = wc._format_standings_table([self._row("Tie", 0, pts=3)])
        self.assertIn("  +0", rendered)


class FormatMatchRowsWithDateTests(unittest.TestCase):
    """Date prefix must live INSIDE backticks so the whole row renders
    in monospace and the date column aligns."""

    def test_date_prefix_inside_backticks(self):
        sched = wc._build_match_dict(EVENT_SCHEDULED)
        sched["date"] = "06/12"
        big = wc._build_match_dict(EVENT_LIVE_BIG_SCORE)
        big["date"] = "06/15"
        rows = wc._format_match_rows([sched, big], show_date=True)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertTrue(row.startswith("`"))
            self.assertTrue(row.endswith("`"))
            self.assertFalse(
                row.startswith("06/"),
                f"date leaked outside backticks: {row!r}",
            )
            inner = row.strip("`").split(" | ", 1)[0]
            self.assertIn("06/", inner)


class EspnDateParamTests(unittest.TestCase):
    """ESPN's `dates=` query param uses YYYYMMDD (no dashes)."""

    def test_format_single_date(self):
        import datetime as _dt
        d = _dt.datetime(2026, 6, 11)
        self.assertEqual(wc._espn_date(d), "20260611")

    def test_format_range(self):
        import datetime as _dt
        start = _dt.datetime(2026, 6, 11)
        end = _dt.datetime(2026, 6, 15)
        self.assertEqual(wc._espn_date_range(start, end), "20260611-20260615")


if __name__ == "__main__":
    unittest.main()
