import discord
from discord.ext import tasks, commands
from urllib.parse import quote as uriquote
import html
from utils.time import human_timedelta
from datetime import datetime
import base64


class Twitter(commands.Cog):
    """All twittery functions like subscribe and lasttweet"""
    def __init__(self, bot):
        self.bot = bot
        # TODO : Disabled for now during porting
        #self.tweet_subscriptions.start()
        self.last_checked = {}

    def cog_unload(self):
        # TODO : Disabled for now during porting
        pass
        #self.tweet_subscriptions.cancel()

    # TODO : Subscribe/unsubscribe functions here. 
    # Need a different config method for subs
    # Preferably something I can keep in-memory with write on add/remove
    # Possibly just a simple json file?
    # consider ignore-retweets on subscription?

    @commands.command(hidden=True)
    @commands.is_owner()
    async def twitter_token(self, ctx):
        auth = f"{self.bot.config.twitterconsumerkey}:{self.bot.config.twitterconsumersecret}"
        auth = "Basic " + base64.b64encode(auth.encode()).decode()
        url = "https://api.twitter.com/oauth2/token"
        body = {"grant_type" : "client_credentials"}
        headers = {"Authorization": auth, "Content-Type" : "application/x-www-form-urlencoded;charset=UTF-8"}
        async with self.bot.session.post(url, data=body, headers=headers) as resp:
            response = await resp.json()
            print(response)

    @commands.command(name='lasttweet')
    async def last_tweet(self, ctx, *, handle: str):
        """Show the last tweet of a twitter user"""
        tweet = (await self.read_timeline(handle))[0]
        parsed = self.parse_tweet(tweet)
        await ctx.send("{author}: {text} ({ago})".format(**parsed))

    @commands.command(hidden=True)
    async def trump(self, ctx):
        """Show trump's most recent words of wisdom"""
        tweet = (await self.read_timeline('realDonaldTrump'))[0]
        parsed = self.parse_tweet(tweet)
        await ctx.send("{author}: {text} ({ago})".format(**parsed))

        
    def parse_tweet(self, tweet):
        updated = datetime.strptime(tweet['created_at'], "%a %b %d %H:%M:%S +0000 %Y")
        ago = human_timedelta(updated, brief=True)
        author = tweet['user']['screen_name']
        text = html.unescape(tweet['full_text'].strip())
        return {'author': author, 'text': text, "ago": ago, "updated": updated}


    async def read_timeline(self, user, count=1):
        url = "https://api.twitter.com/1.1/statuses/user_timeline.json"
        params = {"screen_name": user, "count": count, "tweet_mode": "extended"}
        headers = {"Authorization": "Bearer " + self.bot.config.twitter_token}
        async with self.bot.session.get(url, params=params, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                return None

    @tasks.loop(minutes=1.0)
    async def tweet_subscriptions(self):
        """Reads a twitter timeline and posts the result to any channels that sub it"""
        subs = self.bot.config.twitter_subscriptions
        for twitter_nick in subs:      
            if twitter_nick not in self.last_checked:
                    self.last_checked[twitter_nick] = datetime.utcnow()   
            tweets = await self.read_timeline(twitter_nick, count=3)              
            text = ""
            data = None
            # Newest tweets first, so reverse
            for tweet in reversed(tweets):
                data = self.parse_tweet(tweet)
                if data['updated'] > self.last_checked[twitter_nick]:
                    text += data['text'] + "\n"
            for channel in subs[twitter_nick]:
                # a count of 3 per minute seems to work.... 
                if data and text.strip():
                    self.last_checked[twitter_nick] = data['updated']
                    message = f"{data['author']}: {text.strip()}"
                    chan = self.bot.get_channel(channel)
                    if chan:
                        await chan.send(message)


def setup(bot):
    bot.add_cog(Twitter(bot))
