import discord
from bs4 import BeautifulSoup
import aiohttp
import re
import os
import asyncio
from datetime import datetime
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
                            found_ch = []
                            f.seek(0)
                            entries = f.readlines()
                            for item in soup.find_all('item'):
                                title = item.title.contents[0]
                                link = item.link.contents[0]
                                pubdate = item.pubdate.contents[0]
                                match = re.search(r'ISSTH Chapter (\d+)', title)
                                date_obj = datetime.strptime(pubdate, '%a, %d %b %Y %H:%M:%S %z')
                                if match:
                                    date_str = "%d-%d-%d" % (date_obj.year,date_obj.month,date_obj.day)
                                    chapter_id = "%s_%s" % (match.group(1),date_str)
                                    line = '{}|{}|{}\n'.format(
                                        chapter_id,
                                        link,
                                        pubdate
                                    )
                                    found_ch.append(chapter_id)

                                    if chapter_id not in content:
                                        f.write(line)
                                        await self.bot.send_message(self.channel,link)
                        # Stop the file from getting too big
                        if found_ch and entries:
                            with open(self.entries_db,'w',encoding='utf-8') as db:
                                for i,entry in enumerate(entries):
                                    entry_id,entry_link,entry_date = entry.split('|')
                                    if entry_id not in found_ch:
                                        entries[i] = ''
                                db.writelines(entries)
                await asyncio.sleep(300)

            except Exception as e:
                await asyncio.sleep(60)
                self.wuxia_session.close()
                self.wuxia_session = aiohttp.ClientSession()
                continue


def setup(bot):
    bot.add_cog(Wuxia(bot))
