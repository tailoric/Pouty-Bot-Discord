import discord
from bs4 import BeautifulSoup
import aiohttp
import re
import os
import asyncio
class Wuxia:
    def __init__(self, bot):
        self.bot = bot
        self.update_feed = bot.loop.create_task(self._get_update())
        self.entries_db = 'data/wuxia.db'
        self.wuxia_session = aiohttp.ClientSession()
        self.url = 'http://www.wuxiaworld.com/feed/'
        self.channel = discord.Object(id='191787792898981888')
    def __unload(self):
        self.wuxia_session.close()
        self.update_feed.cancel()

    async def _get_update(self):
        while not self.bot.is_closed:
            try:
                async with self.wuxia_session.get(self.url) as response:
                    if response.status == 200:
                        soup = BeautifulSoup(await response.text(), 'html.parser')
                        if not os.path.isfile(self.entries_db):
                            file = open(self.entries_db,'w')
                            file.close()

                        with open(self.entries_db,'r+',encoding='utf-8') as f:
                            content = f.read()
                            for item in soup.find_all('item'):
                                title = item.title.contents[0]
                                link = item.link.contents[0]
                                pubdate = item.pubdate.contents[0]
                                match = re.search(r'ISSTH Chapter (\d+)', title)
                                line = '{} | {} | {}\n'.format(
                                    title,
                                    link,
                                    pubdate
                                )

                                if match and line not in content:
                                    f.write(line)
                                    await self.bot.send_message(self.channel,link)
                await asyncio.sleep(10)

            except Exception as e:
                user = discord.Object(id='300764599068786698')
                await self.bot.send_message(user, str(e))
                await asyncio.sleep(60)
                continue

def setup(bot):
    bot.add_cog(Wuxia(bot))
