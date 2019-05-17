import sqlite3


CMDSTART = "!"

def __init__(self):
    conn = sqlite3.connect("customcommands.sqlite")
    cursor = conn.cursor()
    custom_command.cursor = cursor
    custom_command.conn = conn
    result = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='commands';").fetchone()
    if not result:
        cursor.execute("CREATE TABLE 'commands' ('cmd' TEXT UNIQUE ON CONFLICT REPLACE, 'output' TEXT, 'owner' TEXT);")
        conn.commit()


def command(self, e, adddel):
    for r in e.message.author.roles:
        if r.name == "Admins":
            isadmin = True
    if not isadmin:
        e.output = "nah, admins only"
        return

    if e.input[0] != CMDSTART or len(e.input.split(" ")) < 2:
        e.output = "Format: !{}cmd {}<cmd> <output>".format(adddel, CMDSTART)
        return

    #Currently hard insert so can be used to edit too
    command = e.input[1:].split(" ")[0].lower()
    output = e.input[len(command) + 2:].strip()
    owner = e.hostmask
    
    c = custom_command.cursor
    conn = custom_command.conn
    if adddel == "add":
        c.execute("INSERT INTO commands VALUES (?,?,?)", (command, output, owner))
    elif adddel == "del":
        c.execute("DELETE FROM commands WHERE cmd = (?)", [command])
    conn.commit()

def del_command(self, e):
    command(self, e, 'del')
del_command.command = "!delcmd"

def add_command(self, e):
    command(self, e, 'add')
add_command.command = "!addcmd"

async def custom_command(self, e):
    c = custom_command.cursor
    if e.input[0] == CMDSTART:
        result = c.execute("SELECT output FROM commands WHERE cmd = (?)", [e.input[1:]]).fetchone()
        if not result:
            return
        else:
            e.output += "\n" + result[0]
            e.ouptut = e.output.strip()
            e.allowembed = True
            return e
custom_command.lineparser = True
