"""FIFA World Cup 2026 cog backed by ESPN's public scoreboard.

This cog calls ESPN's undocumented but publicly accessible
``site.api.espn.com`` endpoints — the same ones that power ESPN's own
World Cup widgets. There is no API key, no auth header, and no
configured rate limit on the free path. The trade-off is that the
endpoint is undocumented and could change shape without notice; the
helpers below are intentionally defensive and any drift will surface
as "no parseable matches" rather than a tracebacks-in-channel.

Pure helpers (`_parse_fixture_status`, `_build_match_dict`,
`_format_match_rows`, `_safe_int`, `_safe_score`, `_normalize_group`,
`_extract_standings`, `_espn_date`, `_espn_date_range`) live at module
scope so they can be unit-tested without spinning up Discord or hitting
the network. See ``tests/test_worldcup.py``.
"""
from __future__ import annotations

import asyncio
import datetime
from typing import Optional

import aiohttp
import discord
import pytz
from discord.ext import commands

from utils.time import HumanTime


# ESPN endpoint hosts (note: standings lives under apis/v2, not apis/site/v2).
ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
)
ESPN_STANDINGS = (
    "https://site.api.espn.com/apis/v2/sports/soccer/fifa.world/standings"
)
WC2026_GROUPS = "ABCDEFGHIJKL"  # 12 groups, 48 teams
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10)
NAME_WIDTH = 14  # uniform team-name truncation in monospace tables
EMBED_DESC_LIMIT = 4000

# ESPN's high-level state buckets (``status.type.state``) collapse most
# of the noisy granular ``type.name`` values. We use the granular name
# only to distinguish cancelled/postponed from other ``post``/``pre``
# events, since both of those should suppress the score.
_LIVE_STATES = {"in"}
_FINISHED_STATES = {"post"}
_SCHEDULED_STATES = {"pre"}
_CANCELLED_NAMES = {
    "STATUS_CANCELED",
    "STATUS_CANCELLED",
    "STATUS_POSTPONED",
    "STATUS_ABANDONED",
    "STATUS_SUSPENDED",
    "STATUS_FORFEIT",
}


# ---------------------------------------------------------------------------
# Pure helpers (testable, no I/O)
# ---------------------------------------------------------------------------


def _parse_fixture_status(status_type) -> str:
    """Bucket an ESPN ``status.type`` object.

    ESPN exposes both a granular ``name`` (e.g. ``STATUS_FULL_TIME``)
    and a higher-level ``state`` (``pre``/``in``/``post``). We prefer
    the state for the broad scheduled/live/finished split, then peek at
    the name to peel off cancelled/postponed (which ESPN can report
    under either state).

    Returns one of ``"scheduled" | "live" | "finished" | "cancelled" |
    "unknown"``. Unknown values are surfaced rather than silently
    dropped so the caller can render an "Unknown status" label.
    """
    if not isinstance(status_type, dict):
        return "unknown"
    name = (status_type.get("name") or "").upper()
    state = (status_type.get("state") or "").lower()
    if name in _CANCELLED_NAMES:
        return "cancelled"
    if state in _LIVE_STATES:
        return "live"
    if state in _FINISHED_STATES:
        return "finished"
    if state in _SCHEDULED_STATES:
        return "scheduled"
    return "unknown"


def _safe_int(val) -> int:
    """Best-effort int cast for arithmetic; never raises."""
    if val is None:
        return 0
    try:
        return int(val)
    except (TypeError, ValueError):
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return 0


def _safe_score(val) -> str:
    """Display-friendly score string. ``None`` → ``"-"`` (not ``"0"``).

    ESPN reports scores as strings — including ``"0"``. We must keep
    those as-is and only collapse a true missing value to ``"-"``.
    """
    if val is None:
        return "-"
    s = str(val).strip()
    if not s:
        return "-"
    return s


def _normalize_group(group) -> Optional[str]:
    """Validate and normalize a WC2026 group letter (A–L)."""
    if not group or not isinstance(group, str):
        return None
    g = group.strip().upper()
    if len(g) != 1 or g not in WC2026_GROUPS:
        return None
    return g


def _espn_date(dt: datetime.datetime) -> str:
    """Format a datetime as ESPN's ``YYYYMMDD`` query-param shape."""
    return dt.strftime("%Y%m%d")


def _espn_date_range(start: datetime.datetime, end: datetime.datetime) -> str:
    """Format a date range as ESPN's ``YYYYMMDD-YYYYMMDD`` shape."""
    return f"{_espn_date(start)}-{_espn_date(end)}"


def _pick_competitor(competitors, side):
    """Return the competitor dict whose ``homeAway`` matches ``side``."""
    for c in competitors or ():
        if isinstance(c, dict) and c.get("homeAway") == side:
            return c
    return None


def _build_match_dict(event) -> Optional[dict]:
    """Project an ESPN scoreboard event into a flat render-ready dict.

    Returns ``None`` if the payload is missing required keys, so the
    caller can simply skip malformed entries.
    """
    if not isinstance(event, dict):
        return None
    try:
        status_type = event["status"]["type"]
        competitions = event["competitions"]
        competitors = competitions[0]["competitors"]
    except (KeyError, TypeError, IndexError):
        return None

    home = _pick_competitor(competitors, "home")
    away = _pick_competitor(competitors, "away")
    if not home or not away:
        return None

    try:
        home_name = home["team"]["displayName"]
        away_name = away["team"]["displayName"]
    except (KeyError, TypeError):
        return None

    venue = ""
    try:
        venue = (competitions[0].get("venue") or {}).get("fullName") or ""
    except AttributeError:
        venue = ""

    state = _parse_fixture_status(status_type)
    detail = status_type.get("detail") or status_type.get("shortDetail") or ""

    home_score_disp = _safe_score(home.get("score"))
    away_score_disp = _safe_score(away.get("score"))

    if state == "scheduled":
        status_label = _format_kickoff(event.get("date"), venue) or detail or "Scheduled"
        return {
            "ateam": away_name,
            "hteam": home_name,
            "ascore": "-",
            "hscore": "-",
            "status": status_label,
            "scheduled": True,
            "state": state,
        }
    if state == "live":
        label = detail or "Live"
        return {
            "ateam": away_name,
            "hteam": home_name,
            "ascore": away_score_disp,
            "hscore": home_score_disp,
            "status": label,
            "scheduled": False,
            "state": state,
        }
    if state == "finished":
        return {
            "ateam": away_name,
            "hteam": home_name,
            "ascore": away_score_disp,
            "hscore": home_score_disp,
            "status": detail or "Final",
            "scheduled": False,
            "state": state,
        }
    if state == "cancelled":
        # ESPN's `detail` for cancelled/postponed already reads cleanly
        # ("Canceled" / "Postponed"); fall back to the name token if not.
        label = detail or status_type.get("name", "Cancelled").title()
        return {
            "ateam": away_name,
            "hteam": home_name,
            "ascore": "-",
            "hscore": "-",
            "status": label,
            "scheduled": True,
            "state": state,
        }
    # unknown
    return {
        "ateam": away_name,
        "hteam": home_name,
        "ascore": away_score_disp,
        "hscore": home_score_disp,
        "status": f"Unknown status: {status_type.get('name') or status_type.get('state') or '?'}",
        "scheduled": True,
        "state": state,
    }


def _format_kickoff(iso_date, venue: str) -> Optional[str]:
    """Render a kickoff timestamp; tolerates bad input by returning None."""
    if not isinstance(iso_date, str):
        return None
    try:
        # ESPN dates look like ``2026-06-12T20:00Z`` — fromisoformat in
        # Python 3.11+ handles the trailing ``Z``, but be safe.
        kt = datetime.datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return None
    label = f"<t:{int(kt.timestamp())}:t>"
    if venue:
        label += f" ({venue})"
    return label


def _format_match_rows(matches, show_date: bool = False):
    """Format match dicts as monospace rows with consistent column widths.

    Width math is derived across BOTH scheduled and non-scheduled rows so
    columns line up regardless of input ordering. Each row is wrapped in
    monospace backticks; columns are separated by ``" | "`` between the
    score block and the status block. When ``show_date=True`` the date
    prefix is placed INSIDE the backticks so the whole row renders in
    monospace and the date column aligns with the rest.
    """
    if not matches:
        return []

    lmax = max(len(m["ateam"]) for m in matches)
    rmax = max(len(m["hteam"]) for m in matches)
    slen = max(len(str(m.get("ascore", ""))) for m in matches)
    slen = max(slen, max(len(str(m.get("hscore", ""))) for m in matches), 1)

    date_width = 0
    if show_date:
        date_width = max((len(str(m.get("date") or "")) for m in matches),
                         default=0)

    rows = []
    for m in matches:
        ateam = m["ateam"].ljust(lmax)
        hteam = m["hteam"].ljust(rmax)
        ascore = str(m["ascore"]).rjust(slen)
        hscore = str(m["hscore"]).ljust(slen)
        if show_date:
            date_str = str(m.get("date") or "").ljust(date_width)
            prefix = f"{date_str} - " if date_width else ""
        else:
            prefix = ""
        rows.append(
            f"`{prefix}{ateam} {ascore} - {hscore} {hteam} | {m['status']}`"
        )
    return rows


def _pluck_stat(stats, name):
    """Return the numeric value of an ESPN stat entry by name, or 0."""
    if not isinstance(stats, list):
        return 0
    for s in stats:
        if isinstance(s, dict) and s.get("name") == name:
            return _safe_int(s.get("value"))
    return 0


def _extract_standings(payload) -> list:
    """Normalize an ESPN standings payload into a list of groups.

    ESPN's shape: ``{"children": [{"name": "Group A", "standings":
    {"entries": [{"team": ..., "stats": [...]}, ...]}}, ...]}``. Each
    ``entries[].stats`` is a list of ``{"name": str, "value": float,
    "displayValue": str}`` — we pluck by name rather than by index.
    """
    if not isinstance(payload, dict):
        return []
    children = payload.get("children") or []
    out = []
    for grp in children:
        if not isinstance(grp, dict):
            continue
        name = grp.get("name") or "Standings"
        standings = grp.get("standings") or {}
        entries = standings.get("entries") or []
        rows = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            stats = entry.get("stats") or []
            gf = _pluck_stat(stats, "pointsFor")
            ga = _pluck_stat(stats, "pointsAgainst")
            gd_explicit = _pluck_stat(stats, "pointDifferential")
            rows.append({
                "team": (entry.get("team") or {}).get("displayName", "?"),
                "mp": _pluck_stat(stats, "gamesPlayed"),
                "w": _pluck_stat(stats, "wins"),
                "d": _pluck_stat(stats, "ties"),
                "l": _pluck_stat(stats, "losses"),
                "gf": gf,
                "ga": ga,
                # Trust ESPN's pointDifferential if present (it can
                # include rule-of-fair-play deductions), but fall back
                # to the computed value if it's zero AND the sides
                # disagree — keeps the formatter regression-safe.
                "gd": gd_explicit if gd_explicit or gf == ga else gf - ga,
                "pts": _pluck_stat(stats, "points"),
            })
        out.append({"name": name, "rows": rows})
    return out


def _format_standings_table(rows, *, show_gf_ga: bool = False) -> str:
    """Render a standings group as a monospace code block."""
    header = (
        f"{'#':<3}{'Team':<{NAME_WIDTH + 1}}"
        f"{'MP':>3} {'W':>3} {'D':>3} {'L':>3} "
    )
    if show_gf_ga:
        header += f"{'GF':>3} {'GA':>3} "
    header += f"{'GD':>4} {'Pts':>4}"

    lines = ["```", header, "-" * len(header)]
    for i, r in enumerate(rows, start=1):
        team = r["team"][:NAME_WIDTH].ljust(NAME_WIDTH)
        line = (
            f"{i:<3}{team} "
            f"{r['mp']:>3} {r['w']:>3} {r['d']:>3} {r['l']:>3} "
        )
        if show_gf_ga:
            line += f"{r['gf']:>3} {r['ga']:>3} "
        line += f"{r['gd']:>+4} {r['pts']:>4}"
        lines.append(line)
    lines.append("```")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class WorldCup(commands.Cog):
    """Commands for FIFA World Cup 2026 fixtures and standings.

    Backed by ESPN's public scoreboard — no API key, no admin config
    required. Works out of the box.
    """

    def __init__(self, bot):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.errors.CheckFailure):
            return
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"Slow down — try again in {int(error.retry_after)}s.",
                delete_after=5.0,
            )
            return
        self.bot.logger.info(error)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _api_get(self, ctx, url: str, params: Optional[dict] = None):
        """Wrap session.get with timeout + uniform error handling.

        Returns the decoded JSON payload, or ``None`` if the request
        failed (the user has already been notified in that case).
        """
        try:
            async with self.bot.session.get(
                url, params=params or {}, timeout=HTTP_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    if resp.status == 429:
                        await ctx.send("Rate limit hit, try again later.")
                    else:
                        await ctx.send("Connection error, try again later.")
                    return None
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            self.bot.logger.info("WorldCup ESPN error: %r", e)
            await ctx.send("Connection error, try again later.")
            return None

    def _sports_date(self, ctx, date):
        # TODO: extract to shared utils once sports.py is touched.
        if date:
            return date.dt
        tz_name = getattr(getattr(ctx, "author_info", None), "timezone", None)
        if tz_name:
            try:
                return datetime.datetime.now(pytz.timezone(tz_name))
            except pytz.UnknownTimeZoneError:
                self.bot.logger.info("Unknown user timezone, falling back to UTC")
        return datetime.datetime.now(pytz.UTC)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @commands.cooldown(rate=3, per=60, type=commands.BucketType.user)
    @commands.command(aliases=["wc2026", "wc"])
    async def worldcup(self, ctx, *, date: HumanTime = None):
        """Show World Cup 2026 matches for today (or a given date)."""
        target = self._sports_date(ctx, date)
        params = {"dates": _espn_date(target)}
        data = await self._api_get(ctx, ESPN_SCOREBOARD, params)
        if data is None:
            return

        events = data.get("events") or []
        if not events:
            await ctx.send(f"No World Cup matches found for {target.date()}.")
            return

        matches = [_build_match_dict(e) for e in events]
        matches = [m for m in matches if m is not None]
        if not matches:
            await ctx.send(f"No parseable World Cup matches for {target.date()}.")
            return

        rows = _format_match_rows(matches)
        description = "\n".join(rows)
        if len(description) > EMBED_DESC_LIMIT:
            description = description[:EMBED_DESC_LIMIT].rsplit("\n", 1)[0]
            description += "\n_… truncated_"
        embed = discord.Embed(
            title="FIFA World Cup 2026",
            description=description,
            color=0x326295,
        )
        await ctx.send(embed=embed)

    @commands.cooldown(rate=3, per=60, type=commands.BucketType.user)
    @commands.command(aliases=["wcschedule", "wcfixtures"])
    async def worldcupschedule(self, ctx, days: int = 7):
        """Show upcoming World Cup matches for the next N days (1–30)."""
        days = max(1, min(int(days), 30))
        start = datetime.datetime.now(pytz.UTC)
        end = start + datetime.timedelta(days=days)
        params = {"dates": _espn_date_range(start, end)}
        data = await self._api_get(ctx, ESPN_SCOREBOARD, params)
        if data is None:
            return

        events = data.get("events") or []
        if not events:
            await ctx.send(f"No matches scheduled for the next {days} days.")
            return

        matches = []
        for raw in events:
            m = _build_match_dict(raw)
            if m is None:
                continue
            # Skip already-finished matches in the schedule view; the
            # user asked for upcoming.
            if m.get("state") == "finished":
                continue
            iso = raw.get("date")
            try:
                if isinstance(iso, str):
                    kt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
                    m["date"] = kt.strftime("%m/%d")
            except ValueError:
                pass
            matches.append(m)

        if not matches:
            await ctx.send(f"No parseable matches for the next {days} days.")
            return

        rows = _format_match_rows(matches, show_date=True)
        rows = rows[:20]
        description = "\n".join(rows)
        if len(description) > EMBED_DESC_LIMIT:
            description = description[:EMBED_DESC_LIMIT].rsplit("\n", 1)[0]
            description += "\n_… truncated_"
        embed = discord.Embed(
            title=f"World Cup Schedule – Next {days} Days",
            description=description,
            color=0x326295,
        )
        if len(matches) > 20:
            embed.set_footer(text=f"Showing first 20 of {len(matches)} matches")
        await ctx.send(embed=embed)

    @commands.cooldown(rate=3, per=60, type=commands.BucketType.user)
    @commands.command(aliases=["wcstandings", "wctable"])
    async def worldcupstandings(self, ctx):
        """Show World Cup group standings — one embed per group."""
        data = await self._api_get(ctx, ESPN_STANDINGS)
        if data is None:
            return

        groups = _extract_standings(data)
        if not groups:
            await ctx.send("No World Cup standings available yet.")
            return

        for grp in groups:
            description = _format_standings_table(grp["rows"])
            if len(description) > EMBED_DESC_LIMIT:
                description = description[:EMBED_DESC_LIMIT].rsplit("\n", 1)[0]
                description += "\n_… truncated_"
            embed = discord.Embed(
                title=f"World Cup 2026 – {grp['name']}",
                description=description,
                color=0x326295,
            )
            await ctx.send(embed=embed)
            await asyncio.sleep(0)

    @commands.cooldown(rate=3, per=60, type=commands.BucketType.user)
    @commands.command(aliases=["wcgroup"])
    async def worldcupgroup(self, ctx, group: str = None):
        """Show one World Cup group's standings (A–L)."""
        norm = _normalize_group(group)
        if norm is None:
            await ctx.send(
                "Please specify a group letter A–L. Example: `!wcgroup A`"
            )
            return

        data = await self._api_get(ctx, ESPN_STANDINGS)
        if data is None:
            return

        groups = _extract_standings(data)
        target = None
        for grp in groups:
            # ESPN labels groups as "Group A".  If the raw name is the
            # "Standings" fallback (unexpected for fifa.world but cheap
            # to defend against), skip rather than silently matching.
            raw_name = (grp.get("name") or "").strip()
            tokens = raw_name.split()
            if not tokens:
                continue
            label = tokens[-1].upper()
            if len(label) != 1 or label not in WC2026_GROUPS:
                continue
            if label == norm:
                target = grp
                break
        if target is None:
            await ctx.send(f"Group {norm} not found or no data available.")
            return

        description = _format_standings_table(target["rows"], show_gf_ga=True)
        embed = discord.Embed(
            title=f"World Cup 2026 – Group {norm}",
            description=description,
            color=0x326295,
        )
        embed.set_footer(
            text="Top 2 + best 8 third-placed teams advance to Round of 32",
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(WorldCup(bot))
