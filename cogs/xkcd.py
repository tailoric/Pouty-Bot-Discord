from typing import Any, List
from discord import app_commands
from discord.enums import AppCommandOptionType, AppCommandType
from discord.ext import commands, tasks
from lxml import html
from thefuzz import fuzz
import discord
from heapq import heappush, nlargest
import logging
from io import BytesIO, StringIO
from datetime import time, timezone
from itertools import islice

from dataclasses import dataclass, field

@dataclass(order=True)
class CompletionResults:
    priority: int
    item: Any=field(compare=False)

class Xkcd(commands.GroupCog, group_name="xkcd"):
    """Commands for searching xkcd comics"""

    def __init__(self, bot):
        self.bot = bot
        self.base_url = "https://xkcd.com"
        self.pages = {}

    async def refresh_page_cache(self):
        async with self.bot.session.get(self.base_url + "/archive/", raise_for_status=True) as response:
            tree = html.fromstring(await response.text())
            for link in tree.iterfind('.//div[@id="middleContainer"]/a'):
                self.pages[link.get('href')[1:-1]] = link.text_content()

    async def cog_load(self) -> None:
        await self.refresh_page_cache()
        self.page_cache_task.start()

    async def cog_unload(self) -> None:
        self.page_cache_task.cancel()

    @tasks.loop(time=time(hour=0, minute=1, tzinfo=timezone.utc))
    async def page_cache_task(self):
        await self.refresh_page_cache()

    @app_commands.command(name="search")
    async def search(self, interaction: discord.Interaction, *, page: str):
        """
        search for an xkcd comic

        Parameters
        ----------
        page: str
            The comic's number, e.g. 1053 otherwise use completion result
        """
        if page.isdigit() and page in self.pages:
            await interaction.response.send_message(f"{self.base_url}/{page}")
        else:
            await interaction.response.send_message("Please use the autocompletion result or a valid comic number.")

    @search.autocomplete('page')
    async def xkcd_autocompletion(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        results = []
        try:
            if current:
                for number, page in self.pages.items():
                    if current.isdigit() and self.pages.get(current):
                        return [app_commands.Choice(name=f"{self.pages.get(current)} [{current}]", value=current)]
                    else:
                        result = CompletionResults(fuzz.partial_ratio(current.lower(), page.lower()), app_commands.Choice(name=f"{page} [{number}]", value=number))
                    heappush(results, result)
                return [r.item for r in nlargest(5, results, key=lambda k: k.priority)]
            else:
                items = islice(self.pages, 5)
                return [app_commands.Choice(name=f"{self.pages[it]} [{it}]", value=it) for it in items]

        except Exception as e:
            logging.exception(e)
            return []


async def setup(bot):
    await bot.add_cog(Xkcd(bot))
