"""AI Cache module for context compaction.

Manages compaction cache, per-channel settings, and usage logging
in a separate SQLite database (logfiles/ai_cache.db).
"""

import aiosqlite
import os
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS compaction_cache (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    oldest_snowflake INTEGER NOT NULL,
    newest_snowflake INTEGER NOT NULL,
    summary_text TEXT NOT NULL,
    model_used TEXT NOT NULL,
    token_count INTEGER,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    guild_id INTEGER,
    channel_id INTEGER,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (guild_id, channel_id, key)
);

CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    command TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL,
    model TEXT NOT NULL,
    timestamp REAL NOT NULL
);
"""

# Settings defaults and validation bounds
# key: (default, min, max)  — min/max are None for string settings
SETTINGS_SPEC = {
    "compact_days":       (7,    1,    30),
    "raw_hours":          (6,    1,    48),
    "compact_max_tokens": (2000, 500,  10000),
    "recompact_raw_hours": (12,  2,    72),
    "recompact_raw_tokens": (15000, 2000, 100000),
    "search_max_tokens":  (8000, 1000, 50000),
    "answer_model":       ("claude-opus-4.6", None, None),
    "compact_model":      ("claude-sonnet-4.5", None, None),
}

# Hardcoded model pricing: (input $/M tokens, output $/M tokens)
MODEL_PRICING = {
    "claude-opus-4.6":    (15.0, 75.0),
    "claude-sonnet-4.5":  (3.0,  15.0),
}
DEFAULT_PRICING = (10.0, 30.0)


def estimate_tokens(text: str) -> int:
    """Rough token count heuristic."""
    return int(len(text) / 4)


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate USD cost for an API call."""
    price_in, price_out = MODEL_PRICING.get(model, DEFAULT_PRICING)
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


class AICache:
    """Async helper for compaction cache, settings, and usage logging."""

    def __init__(self, logdir: str = "logfiles"):
        self.logdir = logdir
        self.db_path = os.path.join(logdir, "ai_cache.db")
        self._db = None

    async def get_db(self) -> aiosqlite.Connection:
        if self._db is None:
            os.makedirs(self.logdir, exist_ok=True)
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
            await self._db.executescript(SCHEMA)
            await self._db.commit()
        return self._db

    async def close(self):
        if self._db is not None:
            await self._db.close()
            self._db = None

    # ── Cache CRUD ──────────────────────────────────────────────

    async def get_cache(self, channel_id: int):
        """Return cache row as dict, or None."""
        db = await self.get_db()
        cursor = await db.execute(
            "SELECT * FROM compaction_cache WHERE channel_id = ?",
            [channel_id],
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def set_cache(self, channel_id: int, guild_id: int,
                        oldest_snowflake: int, newest_snowflake: int,
                        summary_text: str, model_used: str,
                        token_count: int | None = None):
        """Insert or replace a compaction cache entry."""
        db = await self.get_db()
        now = time.time()
        if token_count is None:
            token_count = estimate_tokens(summary_text)
        await db.execute(
            """INSERT OR REPLACE INTO compaction_cache
               (channel_id, guild_id, oldest_snowflake, newest_snowflake,
                summary_text, model_used, token_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [channel_id, guild_id, oldest_snowflake, newest_snowflake,
             summary_text, model_used, token_count, now, now],
        )
        await db.commit()

    async def delete_cache(self, channel_id: int):
        """Delete cache for a single channel."""
        db = await self.get_db()
        await db.execute(
            "DELETE FROM compaction_cache WHERE channel_id = ?",
            [channel_id],
        )
        await db.commit()

    async def delete_guild_caches(self, guild_id: int):
        """Delete all caches for a guild."""
        db = await self.get_db()
        await db.execute(
            "DELETE FROM compaction_cache WHERE guild_id = ?",
            [guild_id],
        )
        await db.commit()

    async def list_caches(self, guild_id: int):
        """Return all cache entries for a guild."""
        db = await self.get_db()
        cursor = await db.execute(
            "SELECT * FROM compaction_cache WHERE guild_id = ? ORDER BY updated_at DESC",
            [guild_id],
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ── Settings CRUD ───────────────────────────────────────────

    async def get_setting(self, guild_id: int, channel_id: int | None, key: str):
        """Get a setting value with channel→guild fallback.

        Returns the Python-typed value (int/float/str) or the default.
        """
        if key not in SETTINGS_SPEC:
            return None

        db = await self.get_db()
        default_val = SETTINGS_SPEC[key][0]

        # Try channel-specific first
        if channel_id is not None:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE guild_id = ? AND channel_id = ? AND key = ?",
                [guild_id, channel_id, key],
            )
            row = await cursor.fetchone()
            if row is not None:
                return self._cast_setting(key, row["value"])

        # Fallback to guild-wide (channel_id IS NULL)
        cursor = await db.execute(
            "SELECT value FROM settings WHERE guild_id = ? AND channel_id IS NULL AND key = ?",
            [guild_id, key],
        )
        row = await cursor.fetchone()
        if row is not None:
            return self._cast_setting(key, row["value"])

        return default_val

    async def set_setting(self, guild_id: int, channel_id: int | None, key: str, value):
        """Validate and store a setting. Returns (success, error_msg)."""
        if key not in SETTINGS_SPEC:
            return False, f"Unknown setting `{key}`. Valid: {', '.join(SETTINGS_SPEC.keys())}"

        default_val, min_val, max_val = SETTINGS_SPEC[key]

        # Validate
        if min_val is not None and max_val is not None:
            # Numeric setting
            try:
                value = int(value)
            except (ValueError, TypeError):
                return False, f"`{key}` must be an integer."
            if value < min_val or value > max_val:
                return False, f"`{key}` must be between {min_val} and {max_val}."
        else:
            # String setting — just store it
            value = str(value)

        db = await self.get_db()
        await db.execute(
            """INSERT OR REPLACE INTO settings (guild_id, channel_id, key, value, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            [guild_id, channel_id, key, str(value), time.time()],
        )
        await db.commit()
        return True, None

    async def get_all_settings(self, guild_id: int, channel_id: int | None = None):
        """Return dict of all effective settings for a channel."""
        result = {}
        for key in SETTINGS_SPEC:
            result[key] = await self.get_setting(guild_id, channel_id, key)
        return result

    def _cast_setting(self, key: str, raw: str):
        """Cast a raw setting value to the correct type."""
        default_val, min_val, max_val = SETTINGS_SPEC[key]
        if min_val is not None:
            try:
                return int(raw)
            except (ValueError, TypeError):
                return default_val
        return raw

    # ── Usage Logging ───────────────────────────────────────────

    async def log_usage(self, channel_id: int, guild_id: int,
                        command: str, input_tokens: int, output_tokens: int,
                        model: str, cost_usd: float | None = None):
        """Log a single API call."""
        if cost_usd is None:
            cost_usd = calculate_cost(model, input_tokens, output_tokens)
        db = await self.get_db()
        await db.execute(
            """INSERT INTO usage_log
               (channel_id, guild_id, command, input_tokens, output_tokens,
                cost_usd, model, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [channel_id, guild_id, command, input_tokens, output_tokens,
             cost_usd, model, time.time()],
        )
        await db.commit()

    async def get_stats(self, guild_id: int, channel_id: int | None = None):
        """Aggregate usage stats. Returns dict with 7d and all-time breakdowns.

        Structure: {command: {"7d": {calls, tokens, cost}, "all": {calls, tokens, cost}}}
        """
        db = await self.get_db()
        seven_days_ago = time.time() - 7 * 86400

        channel_filter = ""
        params_all = [guild_id]
        params_7d = [guild_id, seven_days_ago]
        if channel_id is not None:
            channel_filter = " AND channel_id = ?"
            params_all.append(channel_id)
            params_7d.append(channel_id)

        stats = {}
        for period, ts_filter, params in [
            ("all", "", params_all),
            ("7d", " AND timestamp > ?", params_7d),
        ]:
            cursor = await db.execute(
                f"""SELECT command,
                       COUNT(*) as calls,
                       SUM(input_tokens + output_tokens) as total_tokens,
                       SUM(cost_usd) as total_cost
                   FROM usage_log
                   WHERE guild_id = ?{channel_filter}{ts_filter}
                   GROUP BY command""",
                params,
            )
            rows = await cursor.fetchall()
            for row in rows:
                cmd = row["command"]
                if cmd not in stats:
                    stats[cmd] = {"7d": {"calls": 0, "tokens": 0, "cost": 0.0},
                                  "all": {"calls": 0, "tokens": 0, "cost": 0.0}}
                stats[cmd][period] = {
                    "calls": row["calls"] or 0,
                    "tokens": row["total_tokens"] or 0,
                    "cost": row["total_cost"] or 0.0,
                }

        # Ensure all commands exist in stats even if zero
        for cmd in ("clai", "sclai", "compaction"):
            if cmd not in stats:
                stats[cmd] = {"7d": {"calls": 0, "tokens": 0, "cost": 0.0},
                              "all": {"calls": 0, "tokens": 0, "cost": 0.0}}

        return stats
