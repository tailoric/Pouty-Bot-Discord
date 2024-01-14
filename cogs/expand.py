from discord.ext.commands.help import Paginator
import httpx
import aiohttp
import asyncio
import discord
import io
import json
import logging
import os
import re
from discord.ext import commands
from discord import app_commands
from functools import partial 
from itertools import filterfalse
from pathlib import Path
from textwrap import shorten
from yt_dlp import YoutubeDL, DownloadError
from typing import Optional

spoiler_regex = re.compile(r"\|\|\s?(?P<link>.+?)\s?\|\|")
DEFAULT_FILE_LIMIT = 8388608
class SpoilerLinkConverter(commands.Converter):
    async def convert(self, ctx, argument):
        if (match := spoiler_regex.search(argument)):
            link = match.group('link')
            return link.strip("<>"), True
        else:
            argument = re.split(r"\s", argument)[0]
            return argument.strip("<>"), False
        

class LinkExpander(commands.Cog):
    """
    A cog for expanding links with multiple images
    """
    def __init__(self, bot):
        if not os.path.exists('export'):
            os.mkdir('export')
        self.bot = bot
        self.httpx = httpx.AsyncClient()
        self.session = aiohttp.ClientSession()
        self.pixiv_headers = {
                "Referer" : "https://pixiv.net"
                }
        self.pixiv_url_regex = re.compile(r".*pixiv.net.*/artworks/(\d+)")
        self.twitter_url_regex = re.compile(r"https://(?:\w*\.)?([vf]x)?tw(i|x)tter\.com/(?P<user>\w+)/status/(?P<post_id>\d+)")
        self.reddit_url_regex = re.compile(r"https?://(?:www)?(?:(?:v|old|new)?\.)?(?:redd\.?it)?(?:.com)?/(?:(?P<video_id>(?!r/)\w{10,15})|r|(?P<short_id>\w{4,8}))(?:/(?P<subreddit>\w+)/(?P<pre_id>s|comments)/(?P<post_id>\w+))?")
        path = Path('config/twitter.json')
        path_streamable = Path('config/streamable.json')
        self.logger = logging.getLogger('PoutyBot')
        if path.exists():
            with path.open('r') as f:
                self.twitter_settings = json.load(f)
                self.twitter_header = {
                        "Authorization" : f"Bearer {self.twitter_settings.get('token')}"
                        }
        else:
            self.logger.warn("No twitter configs found")
            self.twitter_settings = None
            self.twitter_header = None           
        if path_streamable.exists():
            with path_streamable.open('r') as f:
                self.streamable_auth = json.load(f)

    async def cog_unload(self):
        self.bot.loop.create_task(self.httpx.aclose())
        self.bot.loop.create_task(self.session.close())


    @commands.command(name="twitter", aliases=['twt', 'twttr'])
    async def twitter_expand(self, ctx, * ,link: SpoilerLinkConverter):
        """
        expand a twitter link to its images
        """
        await ctx.send("https://twitter.com/TwitterDev/status/1621026986784337922?s=20")


    fclyde = app_commands.Group(name="fclyde", description="get around the clyde filter for upload")

    @fclyde.command(name="link")
    @app_commands.describe(
            link="a link you want to send that doesn't get embedded",
            is_spoiler="specify if the file or image is a spoiler, please",
            warning="The content warning for a spoiler"
            )
    @app_commands.rename(
            is_spoiler="spoiler"
            )
    async def fuck_clyde_link(self, interaction: discord.Interaction, link:str , warning: Optional[str], is_spoiler: bool=False) -> None:
        if is_spoiler and not warning:
            return await interaction.response.send_message("Please set a `warning:` when sending a spoiler", ephemeral=True)
        try:
            await interaction.response.send_message(content=f"{warning} || {link} ||" if is_spoiler else link)
        except discord.HTTPException as e:
            await interaction.followup.send(content=str(e))

async def setup(bot):
    await bot.add_cog(LinkExpander(bot))
