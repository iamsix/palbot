#from utils import ordinal
import re


ordinal = lambda n: "%d%s" % (n,"tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4])

async def json_from_url(bot, url, headers=None):
    async with bot.session.get(url, headers=headers) as resp:
        js = await resp.json()
    return js


tagregex = re.compile(r'<.*?>')
def remove_html_tags(data):
    #removes all html tags from a given string
    return tagregex.sub('', data)
