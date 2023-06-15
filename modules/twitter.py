import discord
from discord.ext import tasks, commands
from urllib.parse import quote as uriquote
import html
from utils.time import human_timedelta
from datetime import datetime
import base64


class Twitter(commands.Cog):
    PUBLIC_TOKEN = "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    """All twittery functions like subscribe and lasttweet"""
    def __init__(self, bot):
        self.bot = bot
    #    self.tweet_subscriptions.start() # pylint: disable=no-member
    #    self.last_checked = {}

    #def cog_unload(self):
    #    self.tweet_subscriptions.cancel() # pylint: disable=no-member

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
        tweet = await self.read_timeline(handle)
        if tweet:
            #print(tweet)
            #parsed = self.parse_tweet(tweet[0])
            e = self.embed_tweet(tweet[0])
            await ctx.send(embed=e)
            #await ctx.send("{author}: {text} ({ago})".format(**parsed))
        else:
            await ctx.send(f"Failed to load tweets from twitter user @{handle}")


    @commands.command(hidden=True)
    async def trump(self, ctx):
        """Show trump's most recent words of wisdom"""
        await self.last_tweet(ctx, handle='realDonaldTrump')

    @commands.command(hidden=True)
    async def musk(self, ctx):
        """Show elon's most recent words of wisdom"""
        await self.last_tweet(ctx, handle='elonmusk')
    
    @commands.command(hidden=True)
    async def kexp(self, ctx):
        """show what's playing on KEXP"""
        # This is in twitter.py for historical reasons
        #await self.last_tweet(ctx, handle='kexpnowplaying')
        url = "https://api.kexp.org/v2/plays/?format=json&limit=1&ordering=-airdate"
        async with self.bot.session.get(url) as res:
            data = await res.json()
            data = data['results'][0]

        await ctx.send(f"{data['artist']} - {data['song']} - {data['album']}")

        

    # TODO Handle retweets better
    def embed_tweet(self, tweet):
        content = tweet['content']['itemContent']['tweet_results']['result']['legacy']
        user = tweet['content']['itemContent']['tweet_results']['result']['core']['user_results']['result']['legacy']
        if 'retweeted_status_result' in content:
            user = content['retweeted_status_result']['result']['core']['user_results']['result']['legacy']
            content = content['retweeted_status_result']['result']['legacy']
        handle = user['screen_name']
        link = f"https://twitter.com/{handle}/status/{content['id_str']}"
        e = discord.Embed(title='Tweet', url=link, color=0x1da1f2)
        verified = "\N{BALLOT BOX WITH CHECK}\N{VARIATION SELECTOR-16}" if user['verified'] else ""
        author = f"{user['name']} (@{handle}){verified}"
        aurl = f"https://twitter.com/{handle}"
        e.set_author(name=author, url=aurl, icon_url=user['profile_image_url_https'])
        e.description = html.unescape(content['full_text'].strip())
        image = None
        if 'media' in content['entities'] and 'media_url_https' in content['entities']['media'][0]:
            image = content['entities']['media'][0]['media_url_https']
        if image and image.lower().endswith(('png', 'jpeg', 'jpg', 'gif', 'webp')):
            e.set_image(url=image)
        
        ts = datetime.strptime(content['created_at'], "%a %b %d %H:%M:%S +0000 %Y")
        e.timestamp = ts

        return e

    def parse_tweet(self, tweet):
        updated = datetime.strptime(tweet['created_at'], "%a %b %d %H:%M:%S +0000 %Y")
        ago = human_timedelta(updated, brief=True)
        author = tweet['user']['screen_name']
        text = html.unescape(tweet['full_text'].strip())
        return {'author': author, 'text': text, "ago": ago, "updated": updated}


    async def read_timeline(self, user, count=5):
        gturl = "https://api.twitter.com/1.1/guest/activate.json"
        gthead = { 'Authorization' : self.PUBLIC_TOKEN}
        async with self.bot.session.post(gturl, headers=gthead) as resp:
            gt = await resp.json()
            gt = gt['guest_token']
        
        gqlh = { 'authorization' : self.PUBLIC_TOKEN,
             "content-type" : "application/json",
             'x-guest-token' : gt,
        }
        rid_url = f"https://twitter.com/i/api/graphql/mCbpQvZAw6zu_4PvuAUVVQ/UserByScreenName?variables=%7B%22screen_name%22%3A%22{user}%22%2C%22withSafetyModeUserFields%22%3Atrue%2C%22withSuperFollowsUserFields%22%3Atrue%7D"
        async with self.bot.session.get(rid_url, headers=gqlh) as resp:
            ridjson = await resp.json()
            rid = ridjson['data']['user']['result']['rest_id']

        tweets_url = f"https://twitter.com/i/api/graphql/3ywp9kIIW-VQOssauKmLiQ/UserTweets?variables=%7B%22userId%22%3A%22{rid}%22%2C%22count%22%3A{count}%2C%22includePromotedContent%22%3Atrue%2C%22withQuickPromoteEligibilityTweetFields%22%3Atrue%2C%22withSuperFollowsUserFields%22%3Atrue%2C%22withDownvotePerspective%22%3Afalse%2C%22withReactionsMetadata%22%3Afalse%2C%22withReactionsPerspective%22%3Afalse%2C%22withSuperFollowsTweetFields%22%3Atrue%2C%22withVoice%22%3Atrue%2C%22withV2Timeline%22%3Atrue%7D&features=%7B%22dont_mention_me_view_api_enabled%22%3Atrue%2C%22interactive_text_enabled%22%3Atrue%2C%22responsive_web_uc_gql_enabled%22%3Afalse%2C%22vibe_tweet_context_enabled%22%3Afalse%2C%22responsive_web_edit_tweet_api_enabled%22%3Afalse%2C%22standardized_nudges_misinfo%22%3Afalse%2C%22responsive_web_enhance_cards_enabled%22%3Afalse%2C%22include_rts%22%3Atrue%7D"
        async with self.bot.session.get(tweets_url, headers=gqlh) as resp:
            tweets = await resp.json()

        entries = tweets['data']['user']['result']['timeline_v2']['timeline']['instructions'][1]['entries']
        # Note I'm only returning non-pinned tweets here so the count might not match
        return entries
    #
        
    @tasks.loop(minutes=1.0)
    async def tweet_subscriptions(self):
        """Reads a twitter timeline and posts the new tweets to any channels that sub it"""
        subs = self.bot.config.twitter_subscriptions
        for twitter_nick in subs:      
            if twitter_nick not in self.last_checked:
                    self.last_checked[twitter_nick] = datetime.utcnow()   
            self.bot.logger.debug(f"Starting tweet loop. Last checked: {self.last_checked}")
            tweets = await self.read_timeline(twitter_nick, count=3)
            self.bot.logger.debug(f"Raw tweetsdata: {tweets}")
            if not tweets:
                continue
            text = ""
            data = None
            # Newest tweets first, so reverse
            for tweet in reversed(tweets):
                data = self.parse_tweet(tweet)
                self.bot.logger.debug(f"I have data {data}")
                if data['updated'] > self.last_checked[twitter_nick]:
                    text += data['text'] + "\n"
            self.bot.logger.debug(f"I have a tweet: {text}")
            for channel in subs[twitter_nick]:
                # a count of 3 per minute seems to work.... 
                if data and text.strip():
                    self.last_checked[twitter_nick] = data['updated']
                    message = f"{data['author']}: {text.strip()}"
                    chan = self.bot.get_channel(channel)
                    if chan:
                        await chan.send(message)


async def setup(bot):
    await bot.add_cog(Twitter(bot))
