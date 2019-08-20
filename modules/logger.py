from discord.ext import commands
import discord
import datetime

class Logger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.files = {}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id not in self.files:
            fn = 'logfiles/{}.log'.format(message.channel.id)
            self.files[message.channel.id] = open(fn, 'a+')

        F = self.files[message.channel.id]
        line = "{}:{}::{}!{} PRIVMSG #{} :{} \n"
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        host = str(message.author).replace('#', '@')
        say = message.clean_content.replace('\n', ' ').replace('\r', ' ')
        say = say.replace("@", "")
        svr = message.channel.id
        nick = message.author.display_name
        nick = nick.replace(' ', '_').replace('!', "_")
        line = line.format(timestamp, svr, nick, host, message.channel.name, say)

        F.write(line)
        F.flush()

    @commands.Cog.listener()
    async def on_member_update(self, old, new):
        if old.display_name == new.display_name:
            return
        # for now only interested in nicks.

        fmt = "{}:{}::{}!{} NICK : {}\n"
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        host = str(old).replace("#", "@")
        oldnick = old.display_name.replace(' ', '_').replace('!', "_")
        newnick = new.display_name.replace(' ', '_').replace('!', "_")

        # this depends...
        for chan in old.guild.channels:
            if chan.id in self.files:
                svr = chan.id
                line = fmt.format(timestamp, svr, oldnick, host, newnick)
                self.files[chan.id].write(line)
                self.files[chan.id].flush()
    
    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if before.type != discord.ChannelType.text:
            return
        if before.topic == after.topic:
            return

        fmt = "{}:{}::#{} TOPIC : {}\n"
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        
        if after.id in self.files:
            line = fmt.format(timestamp, after.id, after.name, after.topic)
            self.files[after.id].write(line)
            self.files[after.id].flush()




def setup(bot):
    bot.add_cog(Logger(bot))
