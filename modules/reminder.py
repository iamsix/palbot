from discord.ext import commands, tasks
import discord
from discord import app_commands
import asyncio
import sqlite3
from datetime import datetime, timezone
from dataclasses import dataclass
import pytz
import dateparser
from zoneinfo import ZoneInfo
# 'when' is not stricyly necessary here, just a convenience thing
# timestamp | Channel | userid | when | remindertext

# TODO: change Reminder.reminders to a dict keyed by timestamp
# then I don't need the task thing at all in the EditReminderView

@dataclass
class ReminderItem:
    channel: int
    user: int
    when: datetime
    message: str

UTC = ZoneInfo("UTC")

class TimePrompt(discord.ui.Modal, title="New reminder time"):
    new_time = None
    reminder: ReminderItem = None
    time = discord.ui.TextInput(label="New Time for the reminder", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        userinfo = interaction.client.utils.AuthorInfo(interaction.user)
        tz = userinfo.timezone
        date = dateparser.parse(self.time.value , 
                                settings={'TIMEZONE': tz, 
                                'PREFER_DATES_FROM': 'future',
                                'RETURN_AS_TIMEZONE_AWARE': True},
                                )
        if date:
            self.new_time = date
            await interaction.response.defer()
        else:
            await interaction.response.send_message(
                f"Failed to parse new date / time. Push button again to try again", 
                ephemeral=True
                )


class EditReminderView(discord.ui.View):
    reminder_item: ReminderItem = None
    reminder = None
    message = None
    task = None
    @discord.ui.button(label="Change time", emoji="⏱️", style=discord.ButtonStyle.gray)
    async def on_click_change(self, interaction: discord.Interaction, button):
        if interaction.user.id == self.reminder_item.user:
            time = TimePrompt()
            time.reminder = self.reminder_item
            await interaction.response.send_modal(time)
            await time.wait()
            if time.new_time:
                await self.reminder.delete_timer(self.reminder_item)
                self.reminder_item.when = time.new_time
                if self.task:
                    self.reminder.reminders.remove(self.task)
                    self.task.cancel()
                out, editbutton = await self.reminder.make_reminder(self.reminder_item)
                self.message.content = out
                self.task = editbutton.task
                await interaction.followup.edit_message(self.message.id, content=out, view=self)
        else:
            await interaction.response.send_message("You didn't create this reminder", ephemeral=True)

    @discord.ui.button(label="Delete Reminder", emoji="🗑️", style=discord.ButtonStyle.red)
    async def on_click_delete(self, interaction: discord.Interaction, button):
        if interaction.user.id == self.reminder_item.user:
            await self.reminder.delete_timer(self.reminder_item)
            if self.task:
                self.reminder.reminders.remove(self.task)
                self.task.cancel()
            await interaction.response.edit_message(content="Reminder deleted.", view=None)
            self.stop()
        else:
            await interaction.response.send_message("You didn't create this reminder", ephemeral=True)
    
    async def on_timeout(self):
        try:
            self.clear_items()
            await self.message.edit(view=None)
        except:
            pass


class Reminder(commands.Cog):
    reminders = set()
    def __init__(self, bot):
        self.bot = bot

        self.conn = sqlite3.connect("reminders.sqlite")
        self.c = self.conn.cursor()

        q = '''CREATE TABLE IF NOT EXISTS 'reminders' ("timestamp" integer, "channel" integer, "user" integer, "when" text, "reminder" text);'''
        self.c.execute(q)
        self.conn.commit()
        self.check_timers.start()


    async def start_timer(self, reminder):
        seconds = max(0,int((reminder.when - datetime.now(UTC)).total_seconds()))
        await asyncio.sleep(seconds)
        await self.call_reminder(reminder)


    async def save_timer(self, reminder: ReminderItem):
        q = "INSERT INTO reminders VALUES (?, ?, ?, ?, ?)"
        self.c.execute(q, (int(reminder.when.timestamp()), 
                           reminder.channel, reminder.user, 
                           str(reminder.when), reminder.message))
        self.conn.commit()

    async def delete_timer(self, reminder: ReminderItem):
        q = "DELETE FROM reminders WHERE timestamp = (?)"
        self.c.execute(q, [int(reminder.when.timestamp())])
        self.conn.commit()


    @tasks.loop(minutes=(60 * 24))
    async def check_timers(self):
        self.bot.logger.info("remindme loop")
        # first we have to cancel all the reminders so that we don't re-create one already on a timer 
        for reminder in self.reminders:
            reminder.cancel()
        self.reminders.clear()
        ts = int(datetime.now(UTC).timestamp())
        ts += 24*60*60
        q = 'SELECT timestamp, channel, user, reminder FROM reminders WHERE timestamp <= ?'
        res = self.c.execute(q, [(ts)])
        #then create any reminder with less than 24hr time
        for row in res:
            when = datetime.fromtimestamp(row[0]).astimezone(UTC)
            reminder = ReminderItem(row[1], row[2], when, row[3])
            await self.set_timer(reminder)


    async def set_timer(self, reminder):
        task = asyncio.create_task(self.start_timer(reminder))
        self.reminders.add(task)
        task.add_done_callback(self.reminders.discard)
        return task


    def reminder_parser(self, line, tz):
        words = line.split(" ")
        date = None
        message = ""
        for i in range(len(words)):
            tempdate = dateparser.parse(
                " ".join(words[:i+1]), 
                settings={'TIMEZONE': tz, 
                        'PREFER_DATES_FROM': 'future',
                        'RETURN_AS_TIMEZONE_AWARE': True},
                )
            if tempdate:
                date = tempdate
                skip = 1
                if words[i+1] == "to":
                    skip = 2
                message = " ".join(words[i+skip:])

        return date, message


    @commands.command()
    async def timetest(self, ctx, *, time):
        tz = ctx.author_info.timezone

        time += " to test"

        date, message = self.reminder_parser(time, tz)
        if tz and date:
            ntz = ZoneInfo(tz)
            utc = ZoneInfo("UTC")
            date = date.replace(tzinfo=ntz).astimezone(tz=utc).replace(tzinfo=None)
        if date:
            await ctx.send(f"<t:{int(date.timestamp())}> {message}")

    # might make this a command group? to delete reminders.
    @app_commands.command()
    @app_commands.guild_only()
    async def remind(self, interaction: discord.Interaction, when: str, what: str):
        """Set a reminder to yourself
        
        Parameters
        -----------
        when: str
            When to remind you
        what: str
            What to remind you of
        """
        userinfo = interaction.client.utils.AuthorInfo(interaction.user)
        tz = userinfo.timezone
        date = dateparser.parse(when, settings={'TIMEZONE': tz, 
                                                'PREFER_DATES_FROM': 'future', 
                                                'RETURN_AS_TIMEZONE_AWARE': True})
        if not date:
            await interaction.response.send_message(
                "I don't understand when you want this done. Try something like `tomorrow at 8pm` or `jan 3rd 2pm` or `in 5 minutes`",
                ephemeral=True,
                )
            return
        
        reminder = ReminderItem(interaction.channel.id, interaction.user.id, date, what)
        out, editbutton = await self.make_reminder(reminder)
        
        msg = await interaction.response.send_message(
            out, 
            view=editbutton, 
            ephemeral=True, 
            delete_after=60)
        editbutton.message = msg.resource

    # @remind.command(name="delete")
    # @app_commands.describe(id='The reminder ID')
    # @app_commands.autocomplete(id=self.reminders_choices)
    # I think I want to makke id a Choice thing instead of autocomplete
    # @app_commands.choices(id=reminders_choices) # not sure if I can provide the interaction?
    async def delete_reminder(self, interaction: discord.Interaction, id: int):
        pass

    async def reminders_choices(interaction: discord.Interaction, id: int):
        pass

    @commands.command(aliases=['remind'])
    @commands.guild_only()
    async def remindme(self, ctx, *, message: str):
        if ctx.invoked_with.lower() == "remind" and message[:3] == "me ":
            message = message[3:]
        tz = ctx.author_info.timezone
        date, what = self.reminder_parser(message, tz)
        if not date:
            await ctx.reply("I don't understand when you want this done. Try something like `tomorrow at 8pm` or `jan 3rd 2pm` or `in 5 minutes` - format is `!remindme <when> <what>`")
            return

        reminder = ReminderItem(ctx.channel.id, ctx.author.id, date, what)
        out, editbutton = await self.make_reminder(reminder)
        
        msg = await ctx.send (out, view=editbutton)
        editbutton.message = msg
    

    async def make_reminder(self, reminder: ReminderItem):
        if reminder.when.tzinfo:
            reminder.when = reminder.when.astimezone(tz=UTC)
        seconds = int((reminder.when - datetime.now(UTC)).total_seconds())
        task = None
        if seconds < 0:
            out = "I can't remind you of something in the past"
        else:
            out = f"I will remind you on <t:{int(reminder.when.timestamp())}>: {reminder.message}"
            if seconds < (24 * 60 * 60):
                task = await self.set_timer(reminder)
        await self.save_timer(reminder)

        editbutton = EditReminderView(timeout=60)
        editbutton.reminder = self
        editbutton.reminder_item = reminder
        editbutton.task = task

        return (out, editbutton)

    async def call_reminder(self, reminder):
        self.bot.logger.info(f"Calling {reminder}")
        channel = self.bot.get_channel(reminder.channel)
        msg = f'<@{reminder.user}>: {reminder.message}'
        user = self.bot.get_user(reminder.user)
        allowed_mentions = discord.AllowedMentions(users=[user], 
                                                   everyone=False, 
                                                   roles=False)
        await channel.send(msg, allowed_mentions=allowed_mentions)

        q = 'DELETE FROM reminders WHERE timestamp <= ?'
        self.c.execute(q, [(int(reminder.when.timestamp()))])
        self.conn.commit()


    async def cog_unload(self):
        self.conn.close()
        self.check_timers.cancel()
        # cancel all the timers here
        for reminder in self.reminders:
            reminder.cancel()

async def setup(bot):
    await bot.add_cog(Reminder(bot))
