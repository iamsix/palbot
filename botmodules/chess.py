
'''this is an unusual one, we'll have to make a class that 'contains' the chess state, 
Since we're using an embed the bot will have to keep track of the embed post and edit it....
there may be situations where it should reprint it though?

In theory we can use some of these helper functions to do 'pvp' chess too, 
but for now it's just everyone in the channel v. bot'''

import botmodules.sunfish as sunfish
import asyncio
import re

def chess(self, e):
    '''starts a chess match'''
    chess.discord = self
    chess.e = e
    chess.instance = sunfish.Position(sunfish.initial, 0, (True, True), (True, True), 0, 0)
    chess.searcher = sunfish.Searcher()

    render_board(chess.instance, newpost=True)


    #if e.input = "reprint" then reprint and change the embed post's ID
# turn this in to a dict[user.ID] to run a game per user.
chess.instance = None
chess.searcher = None
chess.discord = None
chess.currentpost = None
chess.e = None
chess.editmode = False

def play_chess(self, e):
    if chess.instance:
        render_board(chess.instance, newpost=True)
        return #maybe rerender board here.
    else:
        if e.input == "editmode":
            chess.editmode = True
        chess(self, e)
play_chess.command = "!chess"

def resign(self, e):
    e.output = "coward!"
    chess.instance = None
resign.command = "!cresign"

def chess_move(self, e):
    if not chess.instance:
        return
    move = None
    match = re.match('([a-h][1-8])'*2, e.input)
    if match:
        move = parse(match.group(1)), parse(match.group(2))
        if move in chess.instance.gen_moves():
            chess.instance = chess.instance.move(move)
            if chess.editmode:
                render_board(chess.instance.rotate(), topmsg="Your move: {}".format(e.input))
            if chess.instance.score <= -sunfish.MATE_LOWER:
                e.output = "You won!"
                chess.instance = None
                return

            move, score = chess.searcher.search(chess.instance, secs=1)

            if score == sunfish.MATE_UPPER:
                e.output = "Checkmate!\n"
            
            txtmove = "My move: {}".format(render(119-move[0]) + render(119-move[1]))
            if chess.editmode:
                e.output = txtmove
            chess.instance = chess.instance.move(move)
            render_board(chess.instance, topmsg=txtmove)

            if chess.instance.score <= -sunfish.MATE_LOWER:
                e.output += "You lost."
                chess.instance = None
            return


    # Inform the user when invalid
    e.output = "That's a bullshit move and you know it Donny! Move format is like g8f6"
    return

chess_move.command="!cmove"


def parse(c):
    fil, rank = ord(c[0]) - ord('a'), int(c[1]) - 1
    return sunfish.A1 + fil - 10*rank

def render(i):
    rank, fil = divmod(i - sunfish.A1, 10)
    return chr(fil + ord('a')) + str(-rank + 1)

def render_board(board, newpost=False,  topmsg=""):
    msg = "{}\n".format(topmsg)
    uni_pieces = {'r':'\uD83D\uDD4B', 'n':'\uD83D\uDC34', 'b':'\uD83D\uDE4F\uD83C\uDFFF', 
                  'q':'\uD83D\uDC78\uD83C\uDFFF', 'k':'\uD83E\uDD34\uD83C\uDFFF', 'p':'\uD83D\uDC76\uD83C\uDFFF',
                  'R':'\uD83C\uDFF0', 'N':'\uD83D\uDC14', 'B':'\uD83D\uDE4F\uD83C\uDFFB', 
                  'Q':'\uD83D\uDC78\uD83C\uDFFB', 'K':'\uD83E\uDD34\uD83C\uDFFB', 'P':'\uD83D\uDC76\uD83C\uDFFB', 
                  '.':'\u25FB\uFE0F'}
#                  '.':'\u2B1C'}
    for i, row in enumerate(board.board.split()):
        for c, char in enumerate(row.strip()):
            if char == '.':
                if i % 2 == c % 2:
                    msg += '\u25FB\uFE0F ' #white
                else:
                    msg += "\u25FC\uFE0F " #black
            else:
                msg += "{} ".format(uni_pieces[char])
        msg += " {}\n".format(8-i)

       # msg += '{} {}\n'.format(' '.join(uni_pieces.get(p, p) for p in row), 8-i)

    msg += "\uD83C\uDDE6 \uD83C\uDDE7 \uD83C\uDDE8 \uD83C\uDDE9 \uD83C\uDDEA \uD83C\uDDEB \uD83C\uDDEC \uD83C\uDDED \n"
#    msg += " ａ  ｂ  ｃ  ｄ  ｅ  ｆ  ｇ  ｈ \n"
    if chess.editmode and not newpost and chess.currentpost and chess.currentpost.result:
        asyncio.ensure_future(chess.discord.edit_message(chess.currentpost.result(), msg))
    else:
        chess.currentpost = asyncio.ensure_future(chess.discord.send_message(chess.e.source, msg))

