import Levenshtein
import sqlite3
import time
#import threading
import asyncio
import random
import re
import asyncio
import discord
import json
from unidecode import unidecode
# dateID | numquestions | {scores}
# dateID UNiQue = YYYY-MM-DD-# where # = 0 for triviaq, 1-n for trivia sessions
# scores = json string (easiest to work with)


def __init__(self):
    conn = sqlite3.connect("triviascores.sqlite")
    cursor = conn.cursor()
    result = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scores';").fetchone()
    if not result:
        cursor.execute('''CREATE TABLE 'scores' ("dateid" date NOT NULL UNIQUE, numqs integer, "scores" text);''')
        conn.commit()
    conn.close()


def play_trivia(self, e):
    if e.source.name != "trivia":
        e.output = "you can only do that in #trivia"
        return e
    if trivia.gameon or trivia.delaytimer:
        e.output = "Trivia is already running"
        return e
    trivia.bot = self
    trivia.e = e

    e.output = "Trivia started! Use !strivia to stop"
    trivia.questions_asked = 0
    # used for saving
    try:
        trivia.questionlimit = int(e.input)
    except:
        trivia.questionlimit = 10
    trivia.points = {}
    conn = sqlite3.connect("triviascores.sqlite")
    c = conn.cursor()
    sessid = int(c.execute("SELECT Count(*) FROM scores WHERE dateid LIKE (?)",
                           [time.strftime("%Y-%m-%d") + "%"]
                           ).fetchone()[0]
                 )
    sessid += 1
    conn.close()

    trivia.session = sessid
    # ^^^^
    trivia.stoptrivia = False
#    self.botSay(e)
    trivia.bot.send_message(trivia.e.source, trivia.e.output)
    ask_question()

play_trivia.command = "!triviaround"
play_trivia.helptext = """
Usage: !trivia
Starts a 'round' of trivia - it will keep asking questions until you stop it."""


def trivia():
    pass
trivia.gameon = False
trivia.stoptrivia = False
trivia.autohint = True
trivia.hintsgiven = 0
trivia.qtime = 30
trivia.qdelay = 7
trivia.points = {}
trivia.questions_asked = 0
trivia.delaytimer = None
trivia.timer = None
trivia.session = 0
trivia.answer = ""
trivia.question = ""
trivia.hint = ""
trivia.value = 0
trivia.bot = None
trivia.e = None
trivia.qtimestamp = None
trivia.questionlimit = 10

def ask_question(clueid=None):
    conn = sqlite3.connect("clues.db")
    c = conn.cursor()
    rows = int(c.execute("SELECT Count(*) FROM clues").fetchone()[0])
    if not clueid:
        clueid = str(random.randint(1, rows))
    clue = c.execute("SELECT value, category, clue, answer, links \
                      FROM clues \
                      JOIN documents ON clues.id = documents.id \
                      JOIN classifications ON clues.id = classifications.clue_id \
                      JOIN categories ON classifications.category_id = categories.id \
                      WHERE clues.id = (?)", [clueid]).fetchone()

    trivia.bot.logger.info(clue)
    conn.close()

    trivia.answer = clean_answer(clue[3])
    hint = re.sub(r'[a-zA-Z0-9]', "*", trivia.answer, len(trivia.answer))
    trivia.hint = hint

    #Try to highlight the point of the question - only if it's in the middle of a sentence'
    question = clue[2].replace(" this ", " **this** ")
    question = question.replace(" these ", " **these** ")
    links = ""
    # TODO validate these links
    if clue[4].strip():
        links = "\n {}".format(clue[4])
    trivia.value = int(str(clue[0]).replace(",", ""))
    if trivia.value == 0:
        trivia.value = 5000
    trivia.questions_asked += 1
    trivia.question = "**Question** {}: ${}. [ {} ] {}{}\nHint: `{}`".format(trivia.questions_asked,
                                                                        trivia.value,
                                                                        clue[1],
                                                                        question,
                                                                        links,
                                                                        hint
                                                                        )
    trivia.e.output = trivia.question
    trivia.gameon = True
    trivia.qtimestamp = time.time()
    #trivia.bot.botSay(trivia.e)
    asyncio.ensure_future(trivia.bot.send_message(trivia.e.source, trivia.e.output))
    trivia.e.output = "" 
    trivia.hintsgiven = 0
    if trivia.autohint:
         trivia.timer = trivia.bot.loop.call_later(round(trivia.qtime / 2), first_hint)
    else:
         trivia.timer = trivia.bot.loop.call_later(trivia.qtime, failed_aswer)


def tq(self, e):
    if e.source.name != "trivia":
        e.output = ""
        return e
    e.output = trivia.question
    return e
tq.command = "!tq"
tq.helptext = """
Usage: !tq
Repeats the current question."""


def clean_answer(answer):
    #gets rid of articles like 'The' Answer, 'An' Answer, 'A' cat, etc.
    #also removes a few cases like Answer (alternate answer) - removes anything in ()
    #gets rid of the "" marks in "answer"
#    answer = answer.lower()
    answer = answer.replace('"', "")
    answer = re.sub(r'\(.*?\)', '', answer)
    if answer[0:4].lower() == "the ":
        answer = answer[4:]
    if answer[0:3].lower() == "an ":
        answer = answer[3:]
    if answer[0:2].lower() == "a ":
        answer = answer[2:]

    return answer.strip()


def trivia_q(self, e):
    if e.source.name != "trivia":
        e.output = "you can only do that in #trivia"
        return e
    if trivia.gameon or trivia.delaytimer:
        e.output = "Trivia is already running"
        return e

    trivia.questions_asked = 0
    trivia.session = 0
    dateid = "{}-{}".format(time.strftime("%Y-%m-%d"), trivia.session)
    load_scores(dateid)

    clueid = None
    qid = re.search('clue (\d+)', e.input)
    if qid:
        clueid = int(qid.group(1))
    trivia.bot = self
    trivia.e = e
    ask_question(clueid)
trivia_q.command = "!trivia"
trivia_q.helptext = """
Usage: !triviaq
Asks a single question.
The scores are calculated as if all !triviaq were part of a single round - that resets every day at midnight."""


def load_scores(dateid):
    trivia.points = {}
    conn = sqlite3.connect("triviascores.sqlite")
    cursor = conn.cursor()
    result = cursor.execute("SELECT * FROM scores WHERE dateid = (?)", [dateid]).fetchone()
    if result:
        trivia.points = json.loads(result[2])
        trivia.questions_asked = int(result[1])
    conn.close()


def save_scores(dateid):
    conn = sqlite3.connect("triviascores.sqlite")
    cursor = conn.cursor()
    score = json.dumps(trivia.points)
    cursor.execute("INSERT OR REPLACE INTO scores(dateid, numqs, scores) VALUES (?, ?, ?)", (dateid,
                                                                                             trivia.questions_asked,
                                                                                             score)
                   )
    conn.commit()
    conn.close()


# this can definitely get more fancy with the database TODO
def show_points(self, e):
    if e.source.name != "trivia":
        return e
    e.output = "{} - {} questions asked in total".format(str(trivia.points), str(trivia.questions_asked))
    return e
show_points.command = "!triviascore"
show_points.helptext = """
Usage: !score
Returns the score of the current round (the round which last question asked belongs in)"""


def question_time(self, e):
    if e.source.name != "trivia":
        e.output = ""
        return e
    try:
        if int(e.input) >= 5:
            if int(e.input) <= 120:
                trivia.qtime = int(e.input)
            else:
                trivia.qtime = 120
        else:
            trivia.qtime = 5
    except ValueError:
        e.output = "Time to answer: {} seconds".format(str(trivia.qtime))
        return e
question_time.command = "!qtime"
question_time.helptext = """
Usage: !qtime
Returns time you get to answer a question.
Usage: !qtime [time] in seconds
Example: !qtime 30
Sets the amount of time in seconds you get to answer a question. 5 seconds minimum to 120 seconds maximum."""


def question_delay(self, e):
    if e.source.name != "trivia":
        e.output = ""
        return e
    try:
        if int(e.input) >= 1:
            if int(e.input) <= 30:
                trivia.qdelay = int(e.input)
            else:
                trivia.qdelay = 30
        else:
            trivia.qtime = 1
    except ValueError:
        e.output = "Time between questions: {} seconds ".format(str(trivia.qdelay))
        return e
question_delay.command = "!qdelay"
question_delay.helptext = """
Usage: !qdelay
Returns time between questions during a trivia round.
Usage: !qdelay [time] in seconds
Example: !qdelay 10
Sets the amount of time in seconds between questions. 1 second minimum to 30 seconds maximum."""


#The different hint levels are separate functions only because I
#originally wanted to do different things for each hint
def first_hint():
    trivia.hintsgiven += 1
    trivia.value = round(trivia.value / 2)
    trivia.hint = perc_hint(30)
    trivia.e.output = "Hint1 ${}: `{}`".format(trivia.value, trivia.hint)
    asyncio.ensure_future(trivia.bot.send_message(trivia.e.source, trivia.e.output))
    trivia.timer = trivia.bot.loop.call_later(round(trivia.qtime / 6), second_hint)


def second_hint():
    trivia.hintsgiven += 1
    trivia.value = round(trivia.value / 2)
    trivia.hint = perc_hint(45)
    trivia.e.output = "Hint2 ${}: `{}`".format(trivia.value, trivia.hint)
    asyncio.ensure_future(trivia.bot.send_message(trivia.e.source, trivia.e.output))
    trivia.timer = trivia.bot.loop.call_later(round(trivia.qtime / 6), third_hint)


#Might make this show all vowels rather than percent based
def third_hint():
    trivia.hintsgiven += 1
    trivia.value = round(trivia.value / 2)
    trivia.hint = perc_hint(75)
    trivia.e.output = "Hint3 ${}: `{}`".format(trivia.value, trivia.hint)
    asyncio.ensure_future(trivia.bot.send_message(trivia.e.source, trivia.e.output))
    trivia.timer = trivia.bot.loop.call_later(round(trivia.qtime / 6), failed_answer)


def auto_hint(self, e):
    if e.input == "on":
        trivia.autohint = True
    if e.input == "off":
        trivia.autohint = False
auto_hint.command = "!autohint"


def perc_hint(revealpercent):
    letters = [0]
    for i in range(round(len(trivia.answer) * (revealpercent / 100))):
        letters.append(random.randint(0, len(trivia.answer)))
    hint = ""
    for i in range(len(trivia.answer)):
        if i in letters:
            hint += trivia.answer[i]
        else:
            hint += trivia.hint[i]

    return hint


def failed_answer():
    e = trivia.e
    trivia.timer.cancel()
    trivia.gameon = False
    trivia.delaytimer = None
    dateid = "{}-{}".format(time.strftime("%Y-%m-%d"), trivia.session)
    save_scores(dateid)
    e.output = "FAIL! no one guessed the answer: **{}**".format(trivia.answer)
#    trivia.bot.botSay(e)
    asyncio.ensure_future(trivia.bot.send_message(trivia.e.source, trivia.e.output))
    if trivia.questions_asked >= trivia.questionlimit:
        trivia.stoptrivia = True
    if not trivia.stoptrivia:
        trivia.delaytimer = trivia.bot.loop.call_later(trivia.qdelay, ask_question)


def stop_trivia(self, e):
    if e.source.name != "trivia":
        e.output = ""
        return e
    if trivia.gameon:
        if e.input == "cancel":
            e.output = "Trivia will continue"
            trivia.stoptrivia = False
            return e
        else:
            trivia.stoptrivia = True
            e.output = "Trivia Stopped after the answer is given"
            return e
    else:
        trivia.gameon = False
        trivia.timer.cancel()
        trivia.delaytimer.cancel()
        trivia.delaytimer = None
        e.output = "Trivia stopped"
        return e
stop_trivia.command = "!strivia"
stop_trivia.helptext = """
Usage: !strivia
Stops the current round of trivia. If an unanswered question remains the trivia will stop after it's answered.
Usage: !strivia cancel
Cancels a previous !strivia before the unanswered question is answered so that the round continues."""


def make_hint(self, e):
    if e.source.name != "trivia":
        return
    if not trivia.gameon:
        return
    if trivia.autohint:
        #we advance to the next hint AND forefit the time - this can be used to 'throw away' a q

        if trivia.hintsgiven == 0:
            trivia.timer.cancel()
            first_hint()
        elif trivia.hintsgiven == 1:
            trivia.timer.cancel()
            second_hint()
        elif trivia.hintsgiven == 2:
            trivia.timer.cancel()
            third_hint()
        elif trivia.hintsgiven == 3:
            e.output = "No more hints available. Hint3 ${}: `{}`".format(trivia.value, trivia.hint)
        return e
    trivia.value = round(trivia.value / 2)
    hint = ""
    i = 0
    for char in trivia.hint:
        if random.randint(0, 3) == 1 or i == 0:
            hint += trivia.answer[i]
        else:
            hint = hint + char
        i += 1
    trivia.hint = hint
    e.output = "Hint ${}: `{}`".format(trivia.value, hint)

    return e
make_hint.command = "!hint"
make_hint.helptext = """
Usage: !hint
Shows the next hint, or if 3 hints have been given it shows the last hint.
This also forfeits the amount of time you would have gotten between the hints, for example:
If qtime = 30, you normally get 15 seconds to the first hint, and you do !hint 1 second in to the question
you now only have 15 seconds remaining, because you forfeited the remaining 14 seconds.
"""


async def answer_grabber(self, e):
    if e.source.name != "trivia" or e.nick == e.botnick:
        return e
    # There's no need to continuously compute levenshtein ratio of everything or !hint
    if trivia.gameon and e.input.lower() != "!hint":
        guess = unidecode(e.input.lower().strip())
        cleananswer = unidecode(trivia.answer.lower())
        ratio = Levenshtein.ratio(guess, cleananswer)
        # Show the ratio of the guess for tuning
        trivia.bot.logger.info("{}: {} - {:10.4f}%".format(e.nick,e.input,ratio * 100))

        if ratio >= 0.90:
            tmr = "{:.2f}".format(time.time() - trivia.qtimestamp)

            trivia.gameon = False
            trivia.timer.cancel()

            try:
                trivia.points[e.nick]
            except KeyError:
                trivia.points[e.nick] = [0, 0]  # Points, Number of questions

            trivia.points[e.nick][0] += trivia.value
            trivia.points[e.nick][1] += 1

            dateid = "{}-{}".format(time.strftime("%Y-%m-%d"), trivia.session)
            save_scores(dateid)

            e.output = "Winrar in {} seconds! **{}** [ ${} in {} ] got the answer: **{}**".format(tmr,
                                                                                              e.nick,
                                                                                              trivia.points[e.nick][0],
                                                                                              trivia.points[e.nick][1],
                                                                                              trivia.answer)
#            self.botSay(e)
            trivia.bot.send_message(trivia.e.source, trivia.e.output)
            
            if trivia.questions_asked >= trivia.questionlimit:
               trivia.stoptrivia = True


            if trivia.stoptrivia:
                trivia.gameon = False
                trivia.delaytimer = None
            else:
                trivia.delaytimer = trivia.bot.loop.call_later(trivia.qdelay, ask_question)

answer_grabber.lineparser = True


def trivia_help(self, e):
    if e.source.name != "trivia":
        e.output = "You can only do that in #trivia"
        return e
    e.output = """
    Trivia Commands: 
    !triviaround - starts a round of trivia, by default 10 questions. !strivia - Stops a trivia round. - optionally !triviaround # for # of questions
    !trivia - Ask a Single question
    !hint - Show a hint. !score - Show the current score.  !autohint on/off - toggles the auto-hint system
    !qtime [sec] time to answer. !qdelay [sec] time between questions. !tq - Reprints the current question
    For more info PM the bot with !help <command> such as: !help !trivia"""

    return e
trivia_help.command = "!triviahelp"

