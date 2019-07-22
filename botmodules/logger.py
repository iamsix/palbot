# need to either generate logs in a pisg compatible irc-like format, or make all the stats myself. If I make them myself:
# track lines posted, chars per line, last seen, time of lines
# nick changes. 
# The random quote here is difficult because I basically need to log all lines to do it.
# do the lines containing question mark
# do the shift-key thing (all caps)
# not sure smily sad faces are relevent due to emojis....
# most words
# most words per line.
# most used words - not sure how this works... might have to look at pisg
# most referenced nicks
# most referenced urls?
# ----
# probably best to actually make a database here?
# nick | discordID | timestamp | line
# do all the stats stuff by parsing that db the same way pisg works?


# likely much easier to make a thing that outputs "IRC" logs but translate some discord conventions to irc ones.
# things like join/part isn't really applicable.
# ban stats and such aren't applicable.
# actions don't really exist
# mimic psybnc
# 2001-08-19-23-14-06:#LINUX.DE::stelb!user@host.org PRIVMSG #linux.de :hi!
# 2001-08-19-23-14-06:Genmay::Nick!nick#1345 PRIVMSG #thepalship :lolol
# convert the # in the 'hostname' to an @?
# use e.source.name for channel name
# use e.source.server.id likely for servername
# looking at the .pm file most of the channel name and server etc doesn't matter
# might be able to do nicklines here - kick join mode will never happen
# maybe topic?

# best to leave the file open between writes but no way to know what files to open... maybe make some kind of filehandle thing that I can check every time if I have one open.
# {"channel.server", filehandle"}
# p. sure I can put a file handle in a dict? not sure if that'll close it or something....
import datetime

async def irclogger(self, e):
    if e.source.id not in irclogger.files:
        fn = 'logfiles/{}.log'.format(e.source.id)
        irclogger.files[e.source.id] = open(fn, 'a+')

    F = irclogger.files[e.source.id]
    line = "{}:{}::{}!{} PRIVMSG #{} :{} \n"
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    host = e.hostmask.replace('#', '@')
    say = e.message.clean_content.replace('\n', ' ').replace('\r', ' ')
    say = say.replace("@", "")
    svr = e.source.id
    nick = e.message.author.display_name
#    if hasattr(e.message.author, 'nick') and  e.message.author.nick:
#        nick = e.message.author.nick
#    else:
#        nick = e.nick
    nick = nick.replace(' ', '_').replace('!', "_")
    line = line.format(timestamp, svr, nick, host, e.source.name, say)
    irclogger.files[e.source.id].write(line)
    irclogger.files[e.source.id].flush()
    
irclogger.lineparser = True
irclogger.files = {}


def nickchange(old, new):
    # nick changes aren't per channel so this is odd...
    # they are per-server but I have no idea if I can find all channels
    # on that server without some shenanigans here...
    # user.server.channels and get the ids from there...
    #
    # 
    # this event fires on EVERY user update - idle etc...
    # might be able to log joins and parts here if I figure out the states
    #
#    if old.status != new.status:
#        print("{}: {}".format(new.display_name, new.status))
    if old.display_name == new.display_name:
        return
    # for now only interested in nicks.

    fmt = "{}:{}::{}!{} NICK : {}\n"
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    host = str(old).replace("#", "@")
    oldnick = old.display_name.replace(' ', '_').replace('!', "_")
    newnick = new.display_name.replace(' ', '_').replace('!', "_")

    # this depends...
    for chan in old.server.channels:
        if chan.id in irclogger.files:
            svr = chan.id
            line = fmt.format(timestamp, svr, oldnick, host, newnick)
            irclogger.files[chan.id].write(line)
            irclogger.files[chan.id].flush()
nickchange.user_listener = True

