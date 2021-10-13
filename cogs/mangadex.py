# -*- coding: utf-8 -*-

from discord.ext import commands
import discord
import re
import json
from dataclasses import dataclass
from typing import List, Optional
from textwrap import shorten

@dataclass
class Manga:
    _id: str
    title: str
    description: str
    tags: List[str]
    status: Optional[str]
    data: dict
    cover_art: Optional[str]


    def build_cover_url(self, data):
        cover_art = next((c for c in data.get("relationships",[]) if c.get("type") == "cover_art"), None)

        if cover_art:
            self.cover_art =f"https://uploads.mangadex.org/covers/{self._id}/{cover_art['attributes']['fileName']}"
        else:
            self.cover_art = None
    def __init__(self, data):
        self.data = data
        self._id = data.get("id")
        attributes = data.get("attributes", {})
        self.title = attributes.get("title",{}).get("en", None)
        self.description = attributes.get("description", {}).get("en")
        self.tags = list(tag.get("attributes").get("name").get("en") for tag in attributes.get("tags", []))
        self.status = attributes.get("status")
        self.build_cover_url(data)

    @property
    def embed(self) -> discord.Embed:
        _embed = discord.Embed(title=self.title,
                colour=discord.Colour(0xff6740),
                url=f"https://mangadex.org/title/{self._id}"
                )
        _embed.description = shorten(self.description, 500)
        if self.status:
            _embed.add_field(name="Status", value=self.status)
        if self.tags:
            _embed.add_field(name="Tags", value=", ".join(self.tags))
        if self.cover_art:
            _embed.set_thumbnail(url=self.cover_art)
        return _embed


class Mangadex(commands.Cog):
    """Automatic embedding and search command for [mangadex](https://mangadex.org)"""

    def __init__(self, bot):
        self.bot = bot
        self.api_url = "https://api.mangadex.org"
        self.mangadex_url = re.compile(r"https?://mangadex.org/title/(?P<id>[a-f0-9A-F]{8}-(?:[a-f0-9A-F]{4}-){3}[a-f0-9A-F]{12})")
        self.params = "includes[]=cover_art"

    @commands.Cog.listener(name="on_message")
    async def embed_mangadex(self, message: discord.Message) -> None:
        if (match:= self.mangadex_url.search(message.content)):
            async with self.bot.session.get(self.api_url + f"/manga/{match.group('id')}?{self.params}") as resp:
                resp.raise_for_status()
                response = await resp.json()
                attributes = response.get("data").get("attributes")
                manga = Manga(response.get("data"))
                await message.channel.send(embed=manga.embed)
                if message.guild and \
                        message.channel.permissions_for(message.guild.me).manage_messages:
                        await message.edit(suppress=True)


    @commands.command(name="mangadex", aliases=["md"])
    async def mangadex_search(self, ctx: commands.Context, *, query: str) -> None:
        """
        search mangadex for a title
        """
        params = {"title": query, "includes[]": "cover_art", "limit": 1 , "order[relevance]": 'desc'}
        async with self.bot.session.get(self.api_url+f"/manga", params=params) as resp:
            resp.raise_for_status()
            response = await resp.json()
            results = response.get("data", [])
            if not results:
                return await ctx.send("No manga found make sure you typed the title correctly")
            for result in results:
                manga = Manga(result)
                await ctx.send(embed=manga.embed)

def setup(bot):
    bot.add_cog(Mangadex(bot))
