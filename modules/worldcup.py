"""FIFA World Cup 2026 cog backed by API-Football.

This is an alternative implementation of #227 that fixes a hardcoded API
key, mis-modeled status codes, mis-aligned formatters, the WC2026 group
count (12 groups, A–L, not 8), and several other correctness issues.

Pure helpers (`_parse_fixture_status`, `_build_match_dict`,
`_format_match_rows`, `_safe_int`, `_safe_score`, `_normalize_group`,
`_extract_standings`) live at module scope so they can be unit-tested
without spinning up Discord or hitting the network. See
``tests/test_worldcup.py``.
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

from modules.ai_cache import AICache


API_BASE = "https://v3.football.api-sports.io"
WORLD_CUP_LEAGUE_ID = 1
WORLD_CUP_SEASON = 2026
WC2026_GROUPS = "ABCDEFGHIJKL"  # 12 groups, 48 teams
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10)
NAME_WIDTH = 14  # uniform team-name truncation in monospace tables
EMBED_DESC_LIMIT = 4000

_SCHEDULED = {"TBD", "NS"}
_LIVE = {"1H", "2H", "HT", "ET", "P", "LIVE", "BT", "INT"}
_FINISHED = {"FT", "AET", "PEN"}
_CANCELLED = {"CANC", "ABD", "AWD", "WO", "SUSP", "PST"}


# ---------------------------------------------------------------------------
# Pure helpers (testable, no I/O)
# ---------------------------------------------------------------------------


def _parse_fixture_status(code) -> str:
    """Bucket an API-Football short status code.

    Returns one of ``"scheduled" | "live" | "finished" | "cancelled" |
    "unknown"``. Unknown codes are surfaced rather than silently dropped
    so the caller can render an "Unknown status: <code>" label.
    """
    if not code or not isinstance(code, str):
        return "unknown"
    if code in _SCHEDULED:
        return "scheduled"
    if code in _LIVE:
        return "live"
    if code in _FINISHED:
        return "finished"
    if code in _CANCELLED:
        return "cancelled"
    return "unknown"


def _safe_int(val) -> int:
    """Best-effort int cast for arithmetic; never raises."""
    if val is None:
        return 0
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _safe_score(val) -> str:
    """Display-friendly score string. ``None`` → ``"-"`` (not ``"0"``)."""
    if val is None:
        return "-"
    return str(val)


def _normalize_group(group) -> Optional[str]:
    """Validate and normalize a WC2026 group letter (A–L)."""
    if not group or not isinstance(group, str):
        return None
    g = group.strip().upper()
    if len(g) != 1 or g not in WC2026_GROUPS:
        return None
    return g


def _build_match_dict(match) -> Optional[dict]:
    """Project an API-Football match object into a flat render-ready dict.

    Returns ``None`` if the payload is missing required keys, so the
    caller can simply skip malformed entries.
    """
    if not isinstance(match, dict):
        return None
    try:
        fixture = match["fixture"]
        teams = match["teams"]
        status = fixture["status"]
        home_name = teams["home"]["name"]
        away_name = teams["away"]["name"]
        short = status["short"]
    except (KeyError, TypeError):
        return None

    goals = match.get("goals") or {}
    venue = (fixture.get("venue") or {}).get("name") or ""
    state = _parse_fixture_status(short)

    home_score_disp = _safe_score(goals.get("home"))
    away_score_disp = _safe_score(goals.get("away"))

    if state == "scheduled":
        status_label = _format_kickoff(fixture.get("date"), venue) or "Scheduled"
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
        minute = _safe_int(status.get("elapsed"))
        long_label = status.get("long") or short
        return {
            "ateam": away_name,
            "hteam": home_name,
            "ascore": away_score_disp,
            "hscore": home_score_disp,
            "status": f"{minute}' {long_label}",
            "scheduled": False,
            "state": state,
        }
    if state == "finished":
        suffix = ""
        if short == "AET":
            suffix = " AET"
        elif short == "PEN":
            suffix = " Pens"
        return {
            "ateam": away_name,
            "hteam": home_name,
            "ascore": away_score_disp,
            "hscore": home_score_disp,
            "status": f"Final{suffix}",
            "scheduled": False,
            "state": state,
        }
    if state == "cancelled":
        return {
            "ateam": away_name,
            "hteam": home_name,
            "ascore": "-",
            "hscore": "-",
            "status": status.get("long") or f"Cancelled ({short})",
            "scheduled": True,
            "state": state,
        }
    # unknown
    return {
        "ateam": away_name,
        "hteam": home_name,
        "ascore": away_score_disp,
        "hscore": home_score_disp,
        "status": f"Unknown status: {short}",
        "scheduled": True,
        "state": state,
    }


def _format_kickoff(iso_date, venue: str) -> Optional[str]:
    """Render a kickoff timestamp; tolerates bad input by returning None."""
    if not isinstance(iso_date, str):
        return None
    try:
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
    slen = max(
        len(str(m.get("ascore", ""))) for m in matches
    )
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


def _extract_standings(payload) -> list:
    """Normalize an API-Football standings payload into a list of groups."""
    if not isinstance(payload, dict):
        return []
    response = payload.get("response") or []
    if not response:
        return []
    league = (response[0] or {}).get("league") or {}
    raw_groups = league.get("standings") or []
    out = []
    for grp in raw_groups:
        if not grp:
            continue
        name = grp[0].get("group") or "Standings"
        rows = []
        for entry in grp:
            stats = entry.get("all") or {}
            goals = stats.get("goals") or {}
            gf = _safe_int(goals.get("for"))
            ga = _safe_int(goals.get("against"))
            rows.append({
                "team": entry.get("team", {}).get("name", "?"),
                "mp": _safe_int(stats.get("played")),
                "w": _safe_int(stats.get("win")),
                "d": _safe_int(stats.get("draw")),
                "l": _safe_int(stats.get("lose")),
                "gf": gf,
                "ga": ga,
                "gd": gf - ga,
                "pts": _safe_int(entry.get("points")),
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
    """Commands for FIFA World Cup 2026 fixtures and standings."""

    def __init__(self, bot):
        self.bot = bot
        # The API key now lives in ai_cache settings (`api_football_key`)
        # so admins can set it at runtime via `!claiconfig` — same
        # pattern as brave_api_key / glm_api_key. We instantiate our own
        # AICache handle (cheap; just a sqlite wrapper) instead of
        # requiring the Copilot cog to be loaded, mirroring persona.py.
        self.ai_cache = AICache()

    def cog_unload(self):
        asyncio.ensure_future(self.ai_cache.close())

    async def _get_api_key(self, ctx):
        """Fetch the API-Football key from ai_cache settings.

        Returns the key string or ``None``. When ``None``, the user has
        already been notified via ``ctx.send`` with a config hint.
        """
        try:
            key = await self.ai_cache.get_setting(
                ctx.guild.id if ctx.guild else 0, None, "api_football_key"
            )
        except Exception as e:
            self.bot.logger.error("WorldCup ai_cache lookup failed: %r", e)
            await ctx.send("World Cup config lookup failed. Try again later.")
            return None
        if not key:
            await ctx.send(
                "⚙️ FIFA API key not configured. An admin can set it with "
                "`!claiconfig api_football_key <key>`."
            )
            return None
        return key

    @staticmethod
    def _headers_for(api_key: str):
        # Direct api-sports.io endpoint uses x-apisports-key, NOT the
        # RapidAPI gateway headers.
        return {"x-apisports-key": api_key}

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

    async def _api_get(self, ctx, api_key: str, path: str, params: dict):
        """Wrap session.get with timeout + uniform error handling.

        Returns the decoded JSON payload, or ``None`` if the request
        failed (the user has already been notified in that case).
        """
        url = f"{API_BASE}{path}"
        try:
            async with self.bot.session.get(
                url, headers=self._headers_for(api_key), params=params,
                timeout=HTTP_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    if resp.status == 429:
                        await ctx.send("API rate limit reached, try again later.")
                    elif resp.status in (401, 403):
                        self.bot.logger.error(
                            "API-Football auth failure (%s)", resp.status
                        )
                        await ctx.send("API auth failure — check configuration.")
                    else:
                        await ctx.send("Connection error, try again later.")
                    return None
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            self.bot.logger.info("WorldCup API error: %r", e)
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
        api_key = await self._get_api_key(ctx)
        if not api_key:
            return

        target = self._sports_date(ctx, date)
        params = {
            "league": WORLD_CUP_LEAGUE_ID,
            "season": WORLD_CUP_SEASON,
            "date": target.strftime("%Y-%m-%d"),
        }
        data = await self._api_get(ctx, api_key, "/fixtures", params)
        if data is None:
            return

        response = data.get("response") or []
        if not response:
            await ctx.send(f"No World Cup matches found for {target.date()}.")
            return

        matches = [_build_match_dict(m) for m in response]
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
        api_key = await self._get_api_key(ctx)
        if not api_key:
            return

        days = max(1, min(int(days), 30))
        start = datetime.datetime.now(pytz.UTC)
        end = start + datetime.timedelta(days=days)
        params = {
            "league": WORLD_CUP_LEAGUE_ID,
            "season": WORLD_CUP_SEASON,
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
            "status": "NS",
        }
        data = await self._api_get(ctx, api_key, "/fixtures", params)
        if data is None:
            return

        response = data.get("response") or []
        if not response:
            await ctx.send(f"No matches scheduled for the next {days} days.")
            return

        matches = []
        for raw in response:
            m = _build_match_dict(raw)
            if m is None:
                continue
            iso = (raw.get("fixture") or {}).get("date")
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
        api_key = await self._get_api_key(ctx)
        if not api_key:
            return

        data = await self._api_get(
            ctx,
            api_key,
            "/standings",
            {"league": WORLD_CUP_LEAGUE_ID, "season": WORLD_CUP_SEASON},
        )
        if data is None:
            return

        groups = _extract_standings(data)
        if not groups:
            await ctx.send("No World Cup standings available yet.")
            return

        for grp in groups:
            description = _format_standings_table(grp["rows"])
            if len(description) > EMBED_DESC_LIMIT:
                # Mirror the trim pattern used by the other commands so
                # we don't chop mid-line and strand the closing ``` fence.
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
        api_key = await self._get_api_key(ctx)
        if not api_key:
            return

        norm = _normalize_group(group)
        if norm is None:
            await ctx.send(
                "Please specify a group letter A–L. Example: `!wcgroup A`"
            )
            return

        data = await self._api_get(
            ctx,
            api_key,
            "/standings",
            {"league": WORLD_CUP_LEAGUE_ID, "season": WORLD_CUP_SEASON},
        )
        if data is None:
            return

        groups = _extract_standings(data)
        target = None
        for grp in groups:
            # API exposes the group label as e.g. "Group A" or just "A".
            # If _extract_standings emitted the "Standings" fallback (when
            # upstream omits the group field), it can't be matched to a
            # single A–L letter — skip it from the per-group lookup
            # rather than silently matching nothing.
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
