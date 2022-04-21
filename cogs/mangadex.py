# -*- coding: utf-8 -*-

import textwrap
from discord.ext import commands
from discord import app_commands
import discord
import re
from dataclasses import dataclass
from typing import List, Optional, Dict
from textwrap import shorten
import datetime
import uuid
import asyncio

@dataclass
class Manga:
    _id: str
    title: str
    description: str
    data: dict

    def __init__(self, data):
        self.data = data
        self._id = data.get("id")
        attributes = data.get("attributes", {})
        self.title = attributes.get("title",{}).get("en", None)
        if self.title is None:
            self.title = next(iter(attributes.get("title", {}).values()), self._id)
        self.description = attributes.get("description", {})
        if self.description and isinstance(self.description, dict):
            self.description = self.description.get("en")

class MangaChapter:
    _id: str
    title: str
    chapter: str
    pages: int
    scanlation_group: str


    def __init__(self, data) -> None:
        self.data = data
        self._id = data.get("id")
        attributes = data.get("attributes", {})
        self.title = attributes.get("title")
        self.chapter = attributes.get("chapter")
        self.pages = attributes.get("pages")
        self.published_at = datetime.datetime.fromisoformat(attributes.get("publishAt")) if attributes.get("publishAt") else None
        relationships = data.get("relationships", {})
        manga_data = next(filter(lambda r: r.get("type") == "manga", relationships), None)
        self.manga = None
        if manga_data:
            self.manga = Manga(manga_data)


class Mangadex(commands.Cog):
    """Automatic embedding and search command for [mangadex](https://mangadex.org)"""

    def __init__(self, bot):
        self.bot = bot
        self.api_url = "https://api.mangadex.org"
        self.mangadex_url = re.compile(r"https?://mangadex.org/(?P<type>title|chapter)/(?P<id>[a-f0-9A-F]{8}-(?:[a-f0-9A-F]{4}-){3}[a-f0-9A-F]{12})")
        self.rate_limit = app_commands.Cooldown(rate=5, per=1)

    async def search_for_title(self, title) -> List[Manga]:
        params = {"title": title, "limit": 5 , "order[relevance]": 'desc'}
        wait = self.rate_limit.update_rate_limit()
        if wait:
            await asyncio.sleep(wait)
        async with self.bot.session.get(self.api_url+f"/manga", params=params) as resp:
            resp.raise_for_status()
            response = await resp.json()
            results = response.get("data", [])
            mangas = []
            for result in results:
                mangas.append(Manga(result))
            return mangas

    @app_commands.command(name="mangadex")
    async def app_mangadex_search(self, interaction: discord.Interaction, title: str) -> None:
        """
        Search mangadex.org for manga and post the result in chat.
        """
        try:
            
            uuid.UUID(title[:36])
            await interaction.response.send_message(f"https://mangadex.org/title/{title[:36]}")
        except ValueError:
            await interaction.response.defer()
            manga = next(iter(await self.search_for_title(title)), None)
            if manga:
                await interaction.followup.send(f"https://mangadex.org/title/{manga._id}")
            else:
                await interaction.followup.send("Nothing found")

    @app_mangadex_search.autocomplete('title')
    async def title_autocomplete(self, interaction: discord.Interaction, current: str):
        await interaction.response.defer()
        results = await self.search_for_title(current)
        choices = []
        for result in results:
            choices.append(app_commands.Choice(name=textwrap.shorten(result.title, 100), value=result._id))
        return choices

async def setup(bot: commands.Bot):
    await bot.add_cog(Mangadex(bot))
