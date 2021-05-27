import aiohttp
import discord
import json
import textwrap

from lxml import etree
from io import BytesIO
from urllib import parse
from discord.ext import commands, menus


class WolframImageList(menus.ListPageSource):
    def __init__(self, data, query):
        self.query = query
        super().__init__(data, per_page=1)

    async def format_page(self, menu, entry):
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

    def __init__(self, bot):
        self.bot = bot
        self.json_file = 'data/wolfram.json'
        with open(self.json_file) as f:
            self.api_key = json.load(f)['api_key']
        self.session = aiohttp.ClientSession()

    @commands.group(invoke_without_command=True)
    async def wolfram(self,  ctx, *, query: str):
        """
        Search wolfram alpha for a query 
        """

        url = 'http://api.wolframalpha.com/v2/query'
        params = {'appid': self.api_key, 'input': query, 'format': 'image'}
        async with ctx.typing():
            async with self.session.get(url=url, params=params) as response:
                response.raise_for_status()
                byio = BytesIO(await response.read())
                tree = etree.parse(byio)
                queryresult = tree.getroot()
                if queryresult.get('success') == "true":
                    entries = list(queryresult.iter('pod'))
                    query_string = parse.quote_plus(query)
                    pages = menus.MenuPages(source=WolframImageList(entries, query_string), clear_reactions_after=True)
                    await pages.start(ctx)
                else:
                    await ctx.send("No Results for your query try something else.")



    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())


def setup(bot):
    bot.add_cog(Wolfram(bot))
