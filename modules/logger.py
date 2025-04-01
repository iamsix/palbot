from discord.ext import commands
import discord
from datetime import datetime, timezone
import os
import aiosqlite
import re

NEW_CHANNEL = "INSERT OR IGNORE INTO channels VALUES (?, ?, ?, ?);"
NEW_TOPIC = "INSERT OR IGNORE INTO channel_topics VALUES (?, ?, ?);"

NEW_USER = "INSERT OR IGNORE INTO users VALUES (?, ?, ?);"
NEW_NICK = "INSERT OR IGNORE INTO user_nicks VALUES (?, ?, ?);"
NEW_TAG = "INSERT OR IGNORE INTO user_tags VALUES (?, ?, ?, ?);"

NEW_MESSAGE = "INSERT OR IGNORE INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?);"
EDIT_MESSAGE = "UPDATE messages SET message = (?), attachments = (?) WHERE snowflake = (?);"
DEL_MESSAGE = "UPDATE messages SET deleted = (?) WHERE snowflake = (?);"
NEW_MENTION = "INSERT OR IGNORE INTO message_mentions VALUES (?, ?);"
NEW_REACTION = "INSERT OR IGNORE INTO message_reactions VALUES (?, ?, ?, ?);"

def regexp(expr, item):
    reg = re.compile(expr)
    return reg.search(item) is not None

NEWGUILD = """
CREATE TABLE IF NOT EXISTS 'messages' (
    "snowflake" integer PRIMARY KEY, 
    "user_id" integer,
    "channel_id" integer,
    "message" text,
    "attachments" text,
    "reference_id" integer,
    "deleted" boolean,
    "ephemeral" boolean,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
    );
    
CREATE TABLE IF NOT EXISTS 'message_mentions' (
    "snowflake" integer,
    "user_id" integer,
    PRIMARY KEY (snowflake, user_id),
    FOREIGN KEY (snowflake) REFERENCES messages(snowflake),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    );

CREATE TABLE IF NOT EXISTS 'message_reactions' (
    "timestamp" integer PRIMARY KEY, 
    "snowflake" integer,  -- message id reacted to
    "user_id" integer,
    "reaction" text,
    FOREIGN KEY (snowflake) REFERENCES messages(snowflake),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    );

    
CREATE TABLE IF NOT EXISTS 'users' (
    "user_id" integer PRIMARY KEY, 
    "canon_nick" text, 
    "is_bot" boolean
    );

CREATE TABLE IF NOT EXISTS 'user_nicks' (
    "timestamp" integer PRIMARY KEY, 
    "user_id" integer,
    "nick" text,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    );

CREATE TABLE IF NOT EXISTS 'user_tags' (
    "timestamp" integer PRIMARY KEY, 
    "user_id" integer,
    "tag" text,
    "added" boolean,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    );


CREATE TABLE IF NOT EXISTS 'channels' (
    "channel_id" integer PRIMARY KEY, 
    "guild" integer,
    "name" text,
    "flags" text
    );

CREATE TABLE IF NOT EXISTS 'channel_topics' (
    "timestamp" integer PRIMARY KEY, 
    "channel_id" integer,
    "topic" text,
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
    );    
    """

class Logger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stat_dbs = {}
        self.logdir = "logfiles"
        os.makedirs(self.logdir, exist_ok=True)

    async def get_db(self, guild: discord.Guild) -> aiosqlite.Connection:
        if guild:
            gid = guild.id
        else:
            gid = "None"
        
        if gid in self.stat_dbs:
            return self.stat_dbs[gid]
        else:
            conn = await aiosqlite.connect(f"{self.logdir}/guild_{gid}_log.sqlite")
            await conn.create_function("REGEXP", 2, regexp, deterministic=True)
            c = await conn.cursor()
            await c.executescript(NEWGUILD)
            await conn.commit()
            self.stat_dbs[gid] = conn
            return self.stat_dbs[gid]


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        chan = message.channel
        user = message.author

        #ephemeral messages are weird. They can have a channel ID but not a guild.
        # even when the channel is IN a guild.
        # the message.channel.guild will also be None in that case
        # to associate them with the right guild I have to try get the guild.
        tchan = self.bot.get_channel(chan.id)
        db = await self.get_db(tchan.guild if tchan else None)

        flags = ""
        chtypes = [discord.TextChannel, discord.GroupChannel, discord.Thread]
        if type(chan) in chtypes:
            if hasattr(chan, "nsfw") and chan.nsfw:
                flags = "nsfw"
            chname = chan.name
        else:
            chname = "None"

        if tchan.guild:
            gid = tchan.guild.id
        else:
            gid = "None"

        try:
            await db.execute(NEW_CHANNEL, [chan.id, gid, chname, flags])
        except aiosqlite.ProgrammingError:
            # This means the db connection is closed...
            return
            

        await db.execute(NEW_USER, [user.id, user.name, user.bot])
        attachments = str(message.attachments)
        ref = None
        content = message.clean_content
        if message.reference:
            if message.reference.type == discord.MessageReferenceType.default:
                ref = message.reference.message_id
            elif message.reference.type == discord.MessageReferenceType.forward:
                content = message.message_snapshots[0].content
        # # not sure if I want to log "empty" messages (embed only)...
        # if not content.strip() and not message.attachments:
        #     return
        
        await db.execute(NEW_MESSAGE, [message.id, user.id, chan.id, 
                                content, attachments, 
                                ref, False, message.flags.ephemeral,
                                ])
        
        for ment in message.mentions:
            await db.execute(NEW_MENTION, [message.id, ment.id])
        await db.commit()


    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.clean_content != after.clean_content or \
                    before.attachments != after.attachments:
            tchan = self.bot.get_channel(before.channel.id)
            db = await self.get_db(tchan.guild if tchan else None)
            attch = str(after.attachments)
            await db.execute(EDIT_MESSAGE, [after.clean_content, 
                                        attch,
                                        after.id])
            await db.commit()

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        tchan = self.bot.get_channel(message.channel.id)
        db = await self.get_db(tchan.guild if tchan else None)
        await db.execute(DEL_MESSAGE, [True, message.id])
        await db.commit()


    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        msg = reaction.message
        ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        tchan = self.bot.get_channel(msg.channel.id)
        db = await self.get_db(tchan.guild if tchan else None)
        await db.execute(NEW_REACTION, [ts, msg.id, user.id, str(reaction.emoji)])
        await db.commit()


    @commands.Cog.listener()
    async def on_member_update(self, old, new):
        if (old.roles != new.roles) or (old.nick != new.nick):
            ts = int(datetime.now(timezone.utc).timestamp() * 1000)
            db = await self.get_db(new.guild)
            if old.nick != new.nick:
                await db.execute(NEW_NICK, [ts, new.id, new.nick])
            if old.roles != new.roles:
                if len(new.roles) > len(old.roles):
                    diff = list(set(new.roles).difference(old.roles))
                    for tag in diff:
                        await db.execute(NEW_TAG, [ts, new.id, tag.name, True])
                else:
                    diff = list(set(old.roles).difference(new.roles))
                    for tag in diff:
                        await db.execute(NEW_TAG, [ts, new.id, tag.name, False])
            await db.commit()


    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if before.type != discord.ChannelType.text:
            return
        if before.topic == after.topic:
            return
        # only doing topics for now
        ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        db = await self.get_db(after.guild)
        await db.execute(NEW_TOPIC, [ts, after.id, after.topic])
        await db.commit()


    async def cog_unload(self):
        for db in self.stat_dbs:
            await self.stat_dbs[db].close()

async def setup(bot):
    await bot.add_cog(Logger(bot))
