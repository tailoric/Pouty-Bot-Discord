from discord.ext import commands
import discord
import json
import asyncio
import re
import os
from aiohttp import ClientSession
from .utils.checks import is_owner_or_moderator
from .utils.paginator import FieldPages
from typing import Union, Optional

class Filter(commands.Cog):
    """
    filters messages and removes them
    """

    def __init__(self, bot):
        self.bot = bot
        self.filter_file_path = "config/tenor_giphy_filter.json"
        self.session = ClientSession()
        self.banned_tags = ['lolicon', 'shotacon']

        if os.path.exists(self.filter_file_path):
            with open(self.filter_file_path, "r") as filter_file:
                try:
                    self.settings = json.load(filter_file)
                    self.blacklisted_channels = [self.bot.get_channel(ch_id) for ch_id in self.settings.get("gif_filter_channel")]
                    self.blacklisted_categories = [self.bot.get_channel(ch_id) for ch_id in self.settings.get("gif_filter_category")]
                    self.sticker_blacklist_channels = [self.bot.get_channel(ch_id) for ch_id in self.settings.get("sticker_filter_channel")]
                    self.sticker_blacklist_categories = [self.bot.get_channel(ch_id) for ch_id in self.settings.get("sticker_filter_category")]
                except json.JSONDecodeError:
                    self.settings = None
                    self.blacklisted_channels = []
                    self.blacklisted_categories = []
        else:
            with open(self.filter_file_path, 'w') as f:
                self.settings = { 
                        "gif_filter_channel": [], 
                        "gif_filter_category": [],
                        "sticker_filter_channel": [],
                        "sticker_filter_category": [],
                                }
                json.dump(self.settings, f)
            self.blacklisted_channels = []
            self.blacklisted_categories = []
            self.sticker_blacklist_channels = []
            self.sticker_blacklist_categories = []

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    @commands.Cog.listener("on_message")
    async def filter_stickers(self, message):
        if not message.stickers:
            return
        if message.channel in self.sticker_blacklist_channels or message.channel.category in self.sticker_blacklist_categories:
            await message.delete()
        if isinstance(message.channel, discord.Thread):
            parent = message.parent
            if parent in self.sticker_blacklist_channels or parent.category in self.sticker_blacklist_categories:
                await message.delete()

    @commands.Cog.listener("on_message")
    async def tenor_message_filter(self, message: discord.Message):
        contains_giphy_or_tenor_link_regex = re.compile("https://(media\.)?(tenor|giphy)?.com/")
        match = contains_giphy_or_tenor_link_regex.match(message.content)
        if not match:
            return
        if message.channel in self.blacklisted_channels or message.channel.category in self.blacklisted_categories:
            await message.delete()
        if isinstance(message.channel, discord.Thread) and (message.channel.parent in self.blacklisted_channels
                or message.channel.parent.category in self.blacklisted_categories):
            await message.delete()
    @commands.Cog.listener("on_message")
    async def on_message(self, message):
        contains_nhentai_link = re.compile(r"https?://nhentai\.net/g/(\d+)")
        matches = contains_nhentai_link.findall(message.content)
        for match in matches:
            data = await self.call_nhentai_api(match)
            if not data:
                continue
            tags = [t['name'] for t in data['tags']]
            for tag in tags:
                if tag not in self.banned_tags:
                    continue
                await message.delete()
                await message.channel.send(f"{message.author.mention} your link was deleted because it contained"
                                           f" a forbidden tag: {tag} (Server Rule 5)")
                admin_cog = self.bot.get_cog("Admin")
                if admin_cog and admin_cog.check_channel:
                    await admin_cog.check_channel.send(f"deleted nhentai link by {message.author.mention} "
                                                        f"because it contained a banned tag: {tag}")


    @is_owner_or_moderator()
    @commands.group(name="blsticker", invoke_without_command=True)
    async def sticker_filter(self, ctx, channel: Union[discord.TextChannel, discord.CategoryChannel]):
        """
        add a channel or category to the blacklist to filter stickers
        """
        if not self.settings:
            return await ctx.send("settings not loaded")
        if isinstance(channel, discord.CategoryChannel):
            self.sticker_blacklist_categories.append(channel)
            self.settings.get("sticker_filter_category").append(channel.id)
        elif isinstance(channel, discord.TextChannel):
            self.sticker_blacklist_channels.append(channel)
            self.settings.get("sticker_filter_channel").append(channel.id)
        with open(self.filter_file_path, "w") as f:
            json.dump(self.settings, f)
        await ctx.send("channel added successfully")

    @sticker_filter.command(name="delete")
    async def sticker_filter_delete(self, ctx, channel: Union[discord.TextChannel, discord.CategoryChannel]):
        """
        remove a channel or category from the blacklist
        """
        if ctx.invoked_subcommand is not None:
            return
        if not self.settings:
            return await ctx.send("settings not loaded")
        if isinstance(channel, discord.CategoryChannel):
            self.sticker_blacklist_channels.remove(channel)
            self.settings.get("sticker_filter_category", []).remove(channel.id)
        elif isinstance(channel, discord.TextChannel):
            self.sticker_blacklist_channels.remove(channel)
            self.settings.get("sticker_filter_channel",[]).remove(channel.id)
        with open(self.filter_file_path, "w") as f:
            json.dump(self.settings, f)
        await ctx.send("channel removed successfully")

    @sticker_filter.command(name="list")
    async def sticker_filter_list(self, ctx):
        """
        list all channels that have a sticker blacklist
        """
        entries = [(c.name, c.mention) for c in self.sticker_blacklist_channels]
        entries.extend((c.name, ','.join(channel.mention for channel in c.channels)) for c in self.sticker_blacklist_categories)
        paginator = FieldPages(ctx, entries=entries)
        paginator.embed.title = "List of blacklisted channels"
        await paginator.paginate()

    @is_owner_or_moderator()
    @commands.group(name="bltenor", aliases=["tenor", "giphy"], invoke_without_command=True)
    async def tenor_filter(self, ctx, channel: Union[discord.TextChannel, discord.CategoryChannel]):
        """
        add a channel or category to the blacklist
        """
        if not self.settings:
            return await ctx.send("settings not loaded")
        if isinstance(channel, discord.CategoryChannel):
            self.blacklisted_categories.append(channel)
            self.settings.get("gif_filter_category").append(channel.id)
        elif isinstance(channel, discord.TextChannel):
            self.blacklisted_channels.append(channel)
            self.settings.get("gif_filter_channel").append(channel.id)
        with open(self.filter_file_path, "w") as f:
            json.dump(self.settings, f)
        await ctx.send("channel added successfully")

    @tenor_filter.command(name="delete")
    async def tenor_filter_delete(self, ctx, channel: Union[discord.TextChannel, discord.CategoryChannel]):
        """
        remove a channel or category from the blacklist
        """
        if ctx.invoked_subcommand is not None:
            return
        if not self.settings:
            return await ctx.send("settings not loaded")
        if isinstance(channel, discord.CategoryChannel):
            self.blacklisted_categories.remove(channel)
            self.settings.get("gif_filter_category").remove(channel.id)
        elif isinstance(channel, discord.TextChannel):
            self.blacklisted_channels.remove(channel)
            self.settings.get("gif_filter_channel").remove(channel.id)
        with open(self.filter_file_path, "w") as f:
            json.dump(self.settings, f)
        await ctx.send("channel removed successfully")

    @tenor_filter.command(name="list")
    async def tenor_filter_list(self, ctx):
        """
        list all channels that have a giphy and tenor blacklist
        """
        entries = [(c.name, c.mention) for c in self.blacklisted_channels]
        entries.extend((c.name, ','.join(channel.mention for channel in c.channels)) for c in self.blacklisted_categories)
        paginator = FieldPages(ctx, entries=entries)
        paginator.embed.title = "List of blacklisted channels"
        await paginator.paginate()

    async def check_for_tags(self, message):
        matches = re.findall(r'\b\d{1,6}\b', message)
        for match in matches:
            data = await self.call_nhentai_api(match)
            if not data:
                continue
            for tag in data['tags']:
                if tag['name'] in self.banned_tags:
                    return True, tag['name']
        return False, None

    async def call_nhentai_api(self, id: int):
        
        url = f"https://nhentai.net/api/gallery/{id}"
        async with self.session.get(url) as response:
            if response.status == 200:
                return await response.json()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if not user.guild:
            return
        mod_role = user.guild.get_role(191094827562041345)
        if isinstance(user, discord.Member) and mod_role in user.roles and reaction.emoji == "\N{MICROSCOPE}":
            check_true, tag = await self.check_for_tags(reaction.message.clean_content)
            if check_true:
                await reaction.message.delete()
                admin_cog = self.bot.get_cog("Admin")
                await reaction.message.channel.send(f"{reaction.message.author.mention} message deleted because it was an nhentai id with following tag: {tag} (Server rule 5)")
                if admin_cog and admin_cog.check_channel:
                    await admin_cog.check_channel.send(f"deleted message by {reaction.message.author.mention} "
                                                        f"because it contained a banned tag: {tag}")

    @is_owner_or_moderator()
    @commands.command(name="filter_exception", pass_context=True)
    async def setup_exception_channel(self,  ctx):
        """
        sets up channel as exception for filtering giphy and tenor links
        """
        channel = ctx.message.channel
        self.allowed_channel = channel
        with open(self.filter_file_path, 'w') as filter_file:
            settings = {"channel_id" : channel.id}
            json.dump(settings, filter_file)
        await ctx.send("channel {} setup as exception channel".format(channel.mention))
def setup(bot):
    bot.add_cog(Filter(bot))
