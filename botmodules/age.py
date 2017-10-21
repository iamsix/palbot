import datetime
import dateutil.parser
from dateutil import relativedelta
import sqlite3


def age(self, e):
        
    if e.input:
        if e.message.mentions:
            e.nick = e.message.mentions[0].name
            bday = get_age(e.nick) 
        elif e.input[0:3].lower() == "set":
            set_age(e.nick, e.input[4:])
            bday = get_age(e.nick)
        else:
            bday = e.input
    else:
        try:
            bday = get_age(e.nick)
        except:
            bday = ""
    try:
        bday = dateutil.parser.parse(bday)
    except ValueError:
        bday = None
    if not bday:
        e.output = "That's not a valid birthday. Use `!age set <date>` to set a valid date"
    else:
        now = datetime.datetime.now()
        d = relativedelta.relativedelta(now, bday)
        out = f"{e.nick} is {d.years} years, {d.months} months, and {d.days} days old"
        e.output = out

    return e
age.command = "!age"

age.message = age
age.mentions = None
age.input = "Nov 9 1983"
age.nick = "six"
age(None, age)
print(age.output)

def get_age(user):
    conn = sqlite3.connect('ages.sqlite')
    c = conn.cursor()
    result = c.execute("SELECT date FROM ages WHERE user = ?", [user.lower()]).fetchone()
    c.close()
    if result:
        return result[0]
    else:
        return ""

def set_age(user, data):
    user = user.lower()
    conn = sqlite3.connect('ages.sqlite')
    c = conn.cursor()
    result = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ages';").fetchone()
    if not result:
         c.execute('''create table ages(user text UNIQUE ON CONFLICT REPLACE, date text)''')

    c.execute("INSERT INTO ages values(?, ?)", (user, data))

    conn.commit()
    c.close()
