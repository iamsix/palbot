import discord
from discord.ext import commands
import asyncio

import Levenshtein
import random
import re
from unidecode import unidecode
import time
import sqlite3
import json

CLUE_Q = "SELECT value, category, clue, answer, links \
            FROM clues \
            JOIN documents ON clues.id = documents.id \
            JOIN classifications ON clues.id = classifications.clue_id \
            JOIN categories ON classifications.category_id = categories.id \
            WHERE clues.id = (?)"

# TODO Consider making trivia a separate class that's instatiated each time a command is run
# that way it will be possible to run multiple trivias in 2 different server / trivia channels...
# would have to keep track of the instances per-channel to allow only 1 at a time per channel
# change things like question_time, question_delay, auto_hint to 'channel prefs'
# will mean a change to the score system (per-channel sessions etc..)

class Trivia(commands.Cog):

    # note this method uses channel.send everywhre instead of ctx.send()
    # because I don't want the trivia posts in the context's recent_posts
    # (recent_posts function not yet written 2019-08-19)

    def __init__(self, bot):
        self.bot = bot
        
        self.game_on = False
        self.live_question = False
        self.stop_after_next = False
        self.hints_given = 0
        self.question_time = 30
        self.question_delay = 7
        self.questions_asked = 0
        self.questions_asked_session = 0
        self.question_limit = 10
        self.auto_hint = True
        self.points = {}
        self.hard_mode = False
        self.session = "{}-0".format(time.strftime("%Y-%m-%d"))

        self.answer_timer = None
        self.question_channel = None

        self.clues_conn = sqlite3.connect("clues.db")
        self.clues_c = self.clues_conn.cursor()
        self.clue_count = int(self.clues_c.execute("SELECT Count(*) FROM clues").fetchone()[0])
    

        self.scores_conn = sqlite3.connect("triviascores.sqlite")
        self.scores_c = self.scores_conn.cursor()
        q = "SELECT name FROM sqlite_master WHERE type='table' AND name='scores';"
        result = self.scores_c.execute(q).fetchone()
        if not result:
            q = '''CREATE TABLE 'scores' ("dateid" date NOT NULL UNIQUE, numqs integer, "scores" text);'''
            self.scores_c.execute(q)
            self.scores_conn.commit()

    def cog_unload(self):
        self.clues_conn.close()
        self.scores_conn.close()
        self.stop_after_next = True
        self.game_on = False
        if self.answer_timer:
            self.answer_timer.cancel()

    @commands.group(name='trivia', invoke_without_command=True)
    async def trivia(self, ctx, num_questions: int = 1):
        """Ask trivia questions from Jeopardy
           optionally provide [num_questions] for number of questions to ask (defaults to 1)"""
        if not (await self.trivia_check(ctx)):
            return

        self.question_channel = ctx.channel
        self.game_on = True
        self.questions_asked = 0
        self.question_limit = max(1,min(num_questions, 100))
        self.stop_after_next = False
        self.session = "{}-0".format(time.strftime("%Y-%m-%d"))
        await self.load_scores()

        if num_questions > 1:
            await ctx.channel.send(f"Trivia started: Asking {num_questions} questions")
        await self.ask_question()

    @trivia.command(name='round')
    async def trivia_round(self, ctx, num_questions: int = 10):
        """Start a round of trivia with a separate score from today's scores"""
        if not (await self.trivia_check(ctx)):
            return

        q = "SELECT Count(*) FROM scores WHERE dateid LIKE (?)"
        sessid = int(self.scores_c.execute(q, [time.strftime("%Y-%m-%d") + "%"]).fetchone()[0])
        sessid += 1
        
        self.points = {}
        self.question_channel = ctx.channel
        self.game_on = True
        self.questions_asked = 0
        self.question_limit = num_questions
        self.stop_after_next = False
        self.session = "{}-{}".format(time.strftime("%Y-%m-%d"), sessid)
        await self.load_scores()

        await ctx.channel.send(f"Trivia round `{self.session}` started: Asking {num_questions} questions")
        await self.ask_question()
    
    @trivia.command(name='stop')
    async def stop_trivia(self, ctx):
        """Stop trivia after the next question/immediately if between questions"""
        if not (await self.trivia_check(ctx, must_be_running=True, quiet=True)):
            return
        if self.game_on:
            self.stop_after_next = True
            if self.live_question:
                await ctx.channel.send("Trivia will be stopped after current question")
            else:
                self.answer_timer.cancel()
                self.game_on = False
                await ctx.channel.send("Trivia stopped")

    @trivia.command(name='score')
    async def trivia_score(self, ctx):
        """Show the current score / round score if currently playing a round"""
        if not (await self.trivia_check(ctx, quiet=True)):
            return
        msg = "{} - {} questions asked in total".format(str(self.points), str(self.questions_asked_session))
        await ctx.channel.send(msg)

    @trivia.command(name='time')
    async def question_time(self, ctx, time: int):
        """Set the time in seconds you get to answer the question"""
        if not (await self.trivia_check(ctx, quiet=True)):
            return
        self.question_time = max(min(time, 120), 10)
        await ctx.channel.send(f"Question time set to: {self.question_time} seconds")

    @trivia.command(name='delay')
    async def question_delay(self, ctx, time: int):
        """Set the time delay in seconds between multiple questions"""
        if not (await self.trivia_check(ctx, quiet=True)):
            return
        self.question_delay = max(min(time, 60), 2)
        await ctx.channel.send(f"Delay time between questions set to: {self.question_delay} seconds")

    @trivia.command(name='hard')
    async def hard_mode(self, ctx):
        """Set hard mode (no hints)"""
        self.hard_mode = not self.hard_mode
        #self.auto_hint = not self.hard_mode #disable auto hint in hard mode
        await ctx.channel.send(f"Hard mode has been set to: {self.hard_mode}")

    @trivia.command(name='autohint')
    async def auto_hint(self, ctx):
        """Set hard mode (no hints)"""
        self.auto_hint = not self.auto_hint
        await ctx.channel.send(f"Auto Hint has been set to: {self.auto_hint}")


    @trivia.command(name='help', hidden=True)
    async def trivia_help(self, ctx):
        """Show trivia help"""
        p = ctx.prefix
        out = f"""> `{p}trivia [number of questions]`
> If [number of questions] is provided it will ask that number in a row, otherwise it will ask 1 question by default. 
> All questions asked from this are effectively considered a single 'round' that resets daily.

> `{p}trivia round [number of questions]`
> Starts a round of trivia which has its own score separate from today's score

> `{p}trivia stop` - stops asking questions after the current question ends or immediately if between questions.
> Used for rounds or `{p}trivia 10` etc

> `{p}trivia score` - shows the current score. if playing a round it will show the round score

> `{p}trivia time <seconds>` - Sets the time in seconds to answer a question 
        
> `{p}trivia delay <seconds>` - Sets the time in seconds between asking the next question """

        await ctx.channel.send(out)


    @trivia.error
    @trivia_round.error
    @question_delay.error
    @question_time.error
    async def trivia_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"Invalid input - input is format is `{ctx.prefix}{ctx.command} ##`")
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(error)
        else:
            raise(error)

    async def ask_question(self):
        if not self.game_on:
            return
        clueid = str(random.randint(1, self.clue_count))
        clue = self.clues_c.execute(CLUE_Q, [clueid]).fetchone()

        self.bot.logger.info(clue)

        self.answer = self.clean_answer(clue[3])
        self.hint = re.sub(r'[a-zA-Z0-9]', "*", self.answer, len(self.answer))
        self.compare_answer = unidecode(self.answer.lower())

        question = clue[2].replace(" this ", " **this** ")
        question = question.replace(" these ", " **these** ")

        links = ""
        if clue[4].strip():
            links = "\n {}".format(clue[4])

        self.value = int(str(clue[0]).replace(",", ""))
        if self.value == 0:
            self.value = 5000
        
        self.questions_asked += 1
        self.questions_asked_session += 1
        if self.questions_asked == self.question_limit:
            self.stop_after_next = True

        question_number = self.questions_asked
        if self.session[-2:] == "-0":
            question_number = self.questions_asked_session
        
        wordcount = len(self.hint.split(" "))
        self.question = (f"**Question** {question_number}: ${self.value}. [ {clue[1]} ] {question}"
                         f" [{wordcount}]"
                         f"{links}")
        if not self.hard_mode:
            self.question += f'\nHint: `{self.hint}`'

        await self.question_channel.send(self.question)

        self.live_question = True
        self.timestamp = time.time()
        self.hints_given = 0
        if self.auto_hint:
            qtime = self.question_time/2
            self.answer_timer = asyncio.ensure_future(self.run_later(qtime, task=self.first_hint))
        else:
            qtime = self.question_time
            self.answer_timer = asyncio.ensure_future(self.run_later(qtime, task=self.failed_answer))

    async def run_later(self, sleep: int, task):
        await asyncio.sleep(sleep)
        await task()

    def clean_answer(self, answer):
        """gets rid of articles like 'The' Answer, 'An' Answer, 'A' cat, etc.
           also removes a few cases like Answer (alternate answer) - removes anything in ()
           gets rid of the "" marks in "answer" """
        answer = answer.replace('"', "")
        answer = re.sub(r'\(.*?\)', '', answer)
        if answer[0:4].lower() == "the ":
            answer = answer[4:]
        if answer[0:3].lower() == "an ":
            answer = answer[3:]
        if answer[0:2].lower() == "a ":
            answer = answer[2:]

        return answer.strip()
        

    @commands.command(name='hint')
    async def show_hint(self, ctx):
        """Show a hint for the current question
           It will also forefit the time allotted between the hints"""
        # no auto-hint always gives the same amount of time even with hints
        # could use the self.timestamp to half the time each time but :meh:

        if not (await self.trivia_check(ctx, must_be_running=True)) or not self.live_question:
            #await ctx.channel.send("There's no qestion to give a hint for...")
            return

#        if self.hard_mode:
#            await ctx.channel.send("No hints in hard mode!")
#            return
        
        if self.auto_hint:
            if  self.hints_given == 0:
                self.answer_timer.cancel()
                await self.first_hint()
            elif self.hints_given == 1:
                self.answer_timer.cancel()
                await self.second_hint()
            elif self.hints_given == 2:
                self.answer_timer.cancel()
                await self.third_hint()
            elif self.hints_given == 3:
                await ctx.channel.send(f"No more hints available. Hint3 ${self.value}: `{self.hint}`")
            return
        
        self.value = round(self.value / 2)
        self.hint = self.perc_hint(30)
        await ctx.channel.send(f"Hint ${self.value}: `{self.hint}`")


    #The different hint levels are separate functions only because I
    #originally wanted to do different things for each hint
    async def first_hint(self):
        self.hints_given += 1
        self.value = round(self.value / 2)
        self.hint = self.perc_hint(30)
        await self.question_channel.send(f"Hint1 ${self.value}: `{self.hint}`")
        qtime = round(self.question_time/6)
        self.answer_timer = asyncio.ensure_future(self.run_later(qtime, task=self.second_hint))


    async def second_hint(self):
        self.hints_given += 1
        self.value = round(self.value / 2)
        self.hint = self.perc_hint(45)
        await self.question_channel.send(f"Hint2 ${self.value}: `{self.hint}`")
        qtime = round(self.question_time/6)
        self.answer_timer = asyncio.ensure_future(self.run_later(qtime, task=self.third_hint))


    #Might make this show all vowels or all consonants rather than percent based
    async def third_hint(self):
        self.hints_given += 1
        self.value = round(self.value / 2)
        self.hint = self.perc_hint(75)
        await self.question_channel.send(f"Hint3 ${self.value}: `{self.hint}`")
        qtime = round(self.question_time/6)
        self.answer_timer = asyncio.ensure_future(self.run_later(qtime, task=self.failed_answer))


    def perc_hint(self, revealpercent):
        letters = [0]
        for i in range(round(len(self.answer) * (revealpercent / 100))):
            letters.append(random.randint(0, len(self.answer)))
        hint = ""
        for i in range(len(self.answer)):
            if i in letters:
                hint += self.answer[i]
            else:
                hint += self.hint[i]
        return hint


    async def failed_answer(self):
        if not self.live_question:
            return
        await self.after_question()
        out = f"FAIL! no one guessed the answer: **{self.answer}**"
        await self.question_channel.send(out)
        
    @commands.Cog.listener()
    async def on_message(self, message):
        if not self.game_on or not self.live_question or \
           message.channel.name != "trivia" or \
           message.author.id == self.bot.user.id:
            return

        user = message.author.display_name
        guess = unidecode(message.content.lower())
        ratio = Levenshtein.ratio(guess, self.compare_answer) # pylint: disable=no-member
        self.bot.logger.info("{}: {} - {:10.4f}%".format(user, message.clean_content,ratio * 100))
        if ratio >= 0.88:
            tmr = "{:.2f}".format(time.time() - self.timestamp)
            self.answer_timer.cancel()            

            if user not in self.points:
                self.points[user] = [0,0] # points, questions_answered

            self.points[user][0] += self.value
            self.points[user][1] += 1
            await self.after_question()
            
            out = (f"Winrar in {tmr} seconds! "
                   f"**{user}** [ ${self.points[user][0]} in {self.points[user][1]} ] "
                   f"got the answer: **{self.answer}**")
            
            await message.channel.send(out)


    async def after_question(self):
        self.live_question = False
        await self.save_scores()
        if self.stop_after_next:
            self.game_on = False
            if self.session[-2:] != "-0":
                #this is a trivia round
                msg = f"Round Over - scores are: {self.points} - {self.questions_asked_session} questions asked"
                await self.question_channel.send(msg)
                self.session = "{}-0".format(time.strftime("%Y-%m-%d"))
                await self.load_scores()
        else:
            self.answer_timer = asyncio.ensure_future(self.run_later(self.question_delay, self.ask_question))


    async def trivia_check(self, ctx, must_be_running=False, quiet=False):
        """An in-class check because I need 'self'"""
        if ctx.channel.name != "trivia":
            if not quiet:
                await ctx.channel.send(f"You can only use `{ctx.prefix}{ctx.invoked_with}` in #trivia")
            return False
        elif ctx.author.id == self.bot.user.id:
            return False
        elif self.game_on and not must_be_running:
            if not quiet:
                await ctx.channel.send("Trivia is already running")
            return False
        elif not self.game_on and must_be_running:
            return False
        else:
            return True

    async def load_scores(self):
        self.points = {}
        self.questions_asked_session = 0
        result = self.scores_c.execute("SELECT * FROM scores WHERE dateid = (?)", [self.session]).fetchone()
        if result:
            self.points = json.loads(result[2])
            self.questions_asked_session = int(result[1])

    async def save_scores(self):
        score = json.dumps(self.points)
        q = "INSERT OR REPLACE INTO scores(dateid, numqs, scores) VALUES (?, ?, ?)"
        self.scores_c.execute(q, (self.session, self.questions_asked_session, score))
        self.scores_conn.commit()


def setup(bot):
    bot.add_cog(Trivia(bot))

