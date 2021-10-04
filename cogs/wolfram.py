import aiohttp
import discord
import json
import textwrap
import logging

from lxml import etree
from typing import List
from io import BytesIO
from urllib import parse
from discord.ext import commands, menus
from .utils import views


class WolframPages(menus.MenuPages):

    async def send_initial_message(self, ctx: commands.Context, channel: discord.TextChannel) -> discord.Message:
        """
        Overwrite to send the second page first (essentially skipping the input)
        """
        if self._source.get_max_pages() > 1:
            page = await self._source.get_page(1)
            self.current_page = 1
        else:
            page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        return await channel.send(**kwargs)

class WolframImageList(menus.ListPageSource):
    def __init__(self, data: List[etree.ElementTree] , query: str):
        self.query = query
        super().__init__(data, per_page=1)

    async def format_page(self, menu : views.PaginatedView, entry: etree.ElementTree) -> discord.Embed:
        image = entry.find(".//img")
        title = entry.get('title') or image.get('title', '\u200b')
        embed = discord.Embed(title=textwrap.shorten(title, width=256),
                description=textwrap.shorten(image.get('alt', '\u200b'), width=2048),
                url=f"https://www.wolframalpha.com/input/?i={self.query}",
                colour=discord.Colour(0xff7e00))
        embed.set_image(url=image.get('src'))
        embed.set_footer(text=f"Page {menu.current_page+1}/{self.get_max_pages()}")
        return embed

class Wolfram(commands.Cog):
    """Wolfram Alpha related commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.json_file = 'data/wolfram.json'
        with open(self.json_file) as f:
            self.api_key = json.load(f)['api_key']
        self.session = aiohttp.ClientSession()
        self.logger =  logging.getLogger("PoutyBot")

    @commands.command()
    async def wolfram(self,  ctx: commands.Context, *, query: str):
        """
        Search wolfram alpha for a query 
        """

        url = 'http://api.wolframalpha.com/v2/query'
        params = {'appid': self.api_key, 'input': query, 'format': 'image'}
        try:
            await ctx.trigger_typing()
        except:
            self.logger.exception("Error during typing")
            
        async with self.session.get(url=url, params=params) as response:
            response.raise_for_status()
            byio = BytesIO(await response.read())
            tree = etree.parse(byio)
            queryresult = tree.getroot()
            if queryresult.get('success') == "true":
                entries = list(queryresult.iter('pod'))
                query_string = parse.quote_plus(query)
                view = views.PaginatedView(source=WolframImageList(entries, query_string), timeout=180)
                await view.start(ctx)
            else:
                await ctx.send("No Results for your query try something else.")



    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())


def setup(bot):
    bot.add_cog(Wolfram(bot))
