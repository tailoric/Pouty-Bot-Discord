from discord.ext import commands
import discord
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import json
from datetime import datetime


class RSS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_feed = bot.loop.create_task(self._get_update())
        self.rss_json = 'data/rss.json'
        self.session_tomo = aiohttp.ClientSession()
        self.session_mousou = aiohttp.ClientSession()

    async def _get_update(self):
        with open(self.rss_json) as f:
            data = json.load(f)
            channel = discord.Object(id=data['channel'])
        while not self.bot.is_closed:
            try:
                link, reddit_id = await self.tomo_rss()
                if link is not None:
                    message = '\n**Chapter:** {:s}\n'.format(link)
                    message += '**Discussion:** <https://www.reddit.com/{:s}>'.format(reddit_id)
                    await self.bot.send_message(channel, message)
                link = await self.mousou_rss()
                if link is not None:
                    await self.bot.send_message(channel, link)
                await asyncio.sleep(60)
            except ConnectionError as e:
                print('{}: {}'.format(type(e).__name__, e))

                await asyncio.sleep(10)
                continue

    def __unload(self):
        self.session_tomo.close()
        self.session_mousou.close()
        self.update_feed.cancel()

    async def tomo_rss(self):
        with open(self.rss_json) as f:
            data = json.load(f)
            url = data['tomo_rss']['url']
            auth = aiohttp.BasicAuth(data['tomo_rss']['client_id'], data['tomo_rss']['client_secret'])
            headers = data['tomo_rss']['headers']
            re_url = None
            re_id = None
        async with self.session_tomo.get(url=url, auth=auth, headers=headers) as response:
            if response.status == 200:
                resp = await response.json()
                for entry in resp['data']['children']:
                    created = entry['data']['created_utc']
                    if created > data['tomo_rss']['last_timestamp']:
                        data['tomo_rss']['last_timestamp'] = created
                        with open(self.rss_json, 'w') as f:
                            f.write(str(data).replace('\'', '"'))  # change quotes for valid json file
                        re_url = entry['data']['url']
                        re_id = entry['data']['id']
        return re_url, re_id

    async def mousou_rss(self):
        re_url = None
        with open(self.rss_json) as f:
            data = json.load(f)
            url = data['mousou_rss']['url']

        async with self.session_mousou.get(url) as response:
            if response.status == 200:
                soup = BeautifulSoup(await response.text(), 'html.parser')
                i = 0
                new_timestamp = data['mousou_rss']['last_timestamp']
                for entry in soup.find_all('item'):
                    pubdate = datetime.strptime(entry.pubdate.text, '%Y-%m-%d %H:%M:%S')
                    if pubdate.timestamp() > data['mousou_rss']['last_timestamp']\
                       and 'Mousou Telepathy' in entry.title.text:
                        if i == 0:
                            i = 1
                            new_timestamp= pubdate.timestamp()

                        re_url = entry.link.text
                with open(self.rss_json, 'w') as f:
                        data['mousou_rss']['last_timestamp'] = new_timestamp
                        f.write(str(data).replace('\'', '"'))
        return re_url


def setup(bot):
    bot.add_cog(RSS(bot))
