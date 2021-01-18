import discord
import aiohttp
import asyncio
import re
from datetime import date, datetime
from functools import partial
from discord.ext import commands
from random import choice
from bs4 import BeautifulSoup

def find_question(text):
    soup = BeautifulSoup(text, 'html.parser')
    headers = soup.find_all('h3')
    question = choice(headers)
    q = question.find('qco')
    if not q:
        q = question.find('font', color="#B387FF")
        date = question.find('font', color="#E9EC54")
        print(q, date)
    else:
        date = question.find('dco')
    return question, q, date

class Bill(commands.Cog):
    '''
    Random question and answer from Bill Wurtz' question website
    https://billwurtz.com/questions/questions.html
    '''
    def __init__(self, bot): 
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.date_parse_regex = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{1,2})\s(am|pm)");
    def cog_unload(self):
        loop = self.bot.loop or asyncio.get_event_loop()
        loop.create_task(self.session.close())

    def build_random_url(self):
        today = date.today()
        range_add = 1 if today.month > 1 else 0
        year = choice(range(2016, today.year + range_add))
        if year == 2016:
            month = choice(range(5,13))
        elif year == today.year:
            month = choice(range(1,today))
        else:
            month = choice(range(1,13))
        month = str(month).zfill(2)
        url = f"https://billwurtz.com/questions/questions-{year}-{month}.html"
        print(url)
        return url

    def parse_date(self, date_str):
        match = self.date_parse_regex.search(date_str)
        if (match):
            year = '20'+match.group(3);
            month = match.group(1).zfill(2);
            day = match.group(2).zfill(2);
            hour = int(match.group(4));

            if (match.group(6) == 'pm' and hour < 12):
                hour += 12;

            hour = str(hour).zfill(2);
            minute = match.group(5);

            return f"{year}{month}{day}{hour}{minute}", datetime(int(year), int(month), int(day), int(hour), int(minute))
        return None
        

    @commands.command()
    async def bill(self, ctx):
        '''
        Random question and answer from [Bill Wurtz'](https://www.youtube.com/channel/UCq6aw03lNILzV96UvEAASfQ) question website
        https://billwurtz.com/questions/questions.html
        '''
        async with ctx.typing():
            async with self.session.get(self.build_random_url()) as response:
                if response.status == 200:
                    text = await response.text()
                    to_run = partial(find_question, text)
                    question, q, dco = await self.bot.loop.run_in_executor(None, to_run)
                    question_url = None
                    date = discord.Embed.Empty
                    if dco:
                        date_str, date= self.parse_date(dco.string)
                        question_url = f"https://billwurtz.com/questions/q.php?date={date_str}"
                    if q: 
                        title = q.string
                        if len(title) > 255: 
                            title = f"{title[:252]}..."
                        description = question.next_sibling.string
                        if len(description) > 500:
                            description = f"{description[:500]}..."
                        embed = discord.Embed(title=title, description=description, url=question_url, timestamp=date)
                        await ctx.send(embed=embed)




def setup(bot):
    bot.add_cog(Bill(bot))
