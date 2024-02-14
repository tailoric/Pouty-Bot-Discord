from discord.ext.commands.help import Paginator
from discord.mentions import AllowedMentions
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
from discord.ui import DynamicItem
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
        

class AutomaticExpandDeleteButton(DynamicItem[discord.ui.Button], template=r'expand:delete:(?P<user_id>[0-9]+)'):
    def __init__(self, user_id: int) -> None:
        super().__init__(
                discord.ui.Button(
                    label="Delete",
                    custom_id=f"expand:delete:{user_id}",
                    emoji="\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"
                    )
                )
        self.user_id: int = user_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):
        user_id = int(match['user_id'])
        return cls(user_id)

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        can_delete = False
        if interaction.guild:
            member : discord.Member = interaction.user
            can_delete = member.resolved_permissions.manage_messages
        if interaction.user.id == self.user_id or can_delete:
            return True
        await interaction.response.send_message("You can't delete this message", ephemeral=True)
        return False

    async def callback(self, interaction: discord.Interaction):
        await interaction.message.delete()

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
        self.twitter_url_regex = re.compile(r"https://(?:\w*\.)?(?P<domain>x|twitter)\.com/(?P<user>\w+)/status/(?P<post_id>\d+)")
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

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(AutomaticExpandDeleteButton)

    async def cog_unload(self):
        self.bot.remove_dynamic_items(AutomaticExpandDeleteButton)
        self.bot.loop.create_task(self.httpx.aclose())
        self.bot.loop.create_task(self.session.close())


    @commands.Cog.listener("on_message")
    async def twitter_expand(self, message: discord.Message):
        """
        expand a twitter link to its images
        """
        if message.author.bot:
            return
        if any(bool(embed.video) for embed in message.embeds):
            return
        matches = list(self.twitter_url_regex.finditer(message.content))
        if not matches:
            return
        urls = []
        for match in matches:
            url = re.sub(r"(x|twitter).com", "fxtwitter.com", match.group(0))
            if re.search(r"(\|\|\s*)(.*)(\|\|\s*)", message.content):
                url = f"|| {url} ||"
            urls.append(url)
        url_strings = "\n".join(urls)
        prefix = "" if len(url_strings) >= 3900 else f"converted {len(urls)} twitter url{'s' if len(urls) > 1 else ''} in this message:\n"
        view = discord.ui.View(timeout=None)
        view.add_item(AutomaticExpandDeleteButton(message.author.id))
        msg = await message.channel.send(prefix + url_strings, reference=message, allowed_mentions=AllowedMentions.none(), view=view)
        if msg.embeds:
            for embed in msg.embeds:
                if embed.video:
                    if message.channel.permissions_for(message.guild.me).manage_messages:
                        await message.edit(suppress=True)
                    return
            return await msg.delete()
        else:
            print('waiting for edit')
            def check(_, after):
                return msg.id == after.id
            try:
                _, after = await self.bot.wait_for('message_edit', check=check, timeout=10)
                for embed in after.embeds:
                    if embed.video:
                        if message.channel.permissions_for(message.guild.me).manage_messages:
                            await message.edit(suppress=True)
                        return
                return await msg.delete()
            except asyncio.TimeoutError:
                pass




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
        """
        Make an url embed that would incorrectly be caught by the nsfw filter (aka clyde) and not embed
        """
        if is_spoiler and not warning:
            return await interaction.response.send_message("Please set a `warning:` when sending a spoiler", ephemeral=True)
        try:
            await interaction.response.send_message(content=f"{warning} || {link} ||" if is_spoiler else link)
        except discord.HTTPException as e:
            await interaction.followup.send(content=str(e))

async def setup(bot):
    await bot.add_cog(LinkExpander(bot))
