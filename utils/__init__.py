#from utils import ordinal
import re
from urllib.parse import quote as uriquote
import asyncio
from bs4 import BeautifulSoup
import collections

ordinal = lambda n: "%d%s" % (n,"tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4])



tagregex = re.compile(r'<.*?>')
def remove_html_tags(data):
    #removes all html tags from a given string
    return tagregex.sub('', data)


async def google_for_urls(bot, search_term, *, url_regex=None):
    url = 'https://www.googleapis.com/customsearch/v1?key={}&cx={}&q={}'
    url = url.format(bot.config.gsearchapi, 
            bot.config.gsearchcx, uriquote(search_term))

    async with bot.session.get(url) as resp:
        json = await resp.json()
        if resp.status != 200:
            print(resp, json)
            return
        results = []
        for result in json['items']:
            if url_regex:
                check = re.search(url_regex, result['link'])
                if not check:
                    continue
            results.append(result['link'].replace('%25', '%'))

        return results

async def bs_from_url(bot, url, return_url=False):
    headers = {'User-Agent': 'Mozilla/5.0 PalBot'}
    async with bot.session.get(url, headers=headers) as resp:
        assert "text" in resp.headers['Content-Type']
        data = await resp.read()
        page = BeautifulSoup(data, 'lxml')
        if return_url:
            return page, str(resp.url)
        else:
            return page

def dict_merge(dct, merge_dct):
    for k, v in merge_dct.items():
        if (k in dct and isinstance(dct[k], dict)
                and isinstance(merge_dct[k], collections.Mapping)):
            dict_merge(dct[k], merge_dct[k])
        else:
            dct[k] = merge_dct[k]


