from discord.ext import commands
import discord
import json
import asyncio
import re
import os
from aiohttp import ClientSession
from .utils.checks import is_owner_or_moderator

class Filter(commands.Cog):
    """
    filters messages and removes them
    """

    def __init__(self, bot):
        self.bot = bot
        self.filter_file_path = "data/filter.json"
        self.session = ClientSession()
        self.banned_tags = ['lolicon', 'shotacon']

        if os.path.exists(self.filter_file_path):
            with open(self.filter_file_path, "r") as filter_file:
                try:
                    settings = json.load(filter_file)
                    self.allowed_channel = self.bot.get_channel(settings['channel_id'])
                except json.JSONDecodeError:
                    self.allowed_channel = None
        else:
            open(self.filter_file_path, 'w').close()
            self.allowed_channel = None

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    @commands.Cog.listener("on_message")
    async def on_message(self, message):
        contains_giphy_or_tenor_link_regex = re.compile("https://(media\.)?(tenor|giphy)?.com/")
        match = contains_giphy_or_tenor_link_regex.match(message.content)
        if match and not message.channel == self.allowed_channel:
            await asyncio.sleep(1)
            await message.delete()

    async def check_for_tags(self, message):
        matches = re.findall(r'\b\d{1,6}\b', message)
        if matches:
            for match in matches:
                number = int(match)
                url = f"https://nhentai.net/api/gallery/{number}"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        for tag in data['tags']:
                            if tag['name'] in self.banned_tags:
                                return True, tag['name']
                        return False, None


    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        mod_role = user.guild.get_role(191094827562041345)
        search_emoji = self.bot.get_emoji(595953208556257292)
        if isinstance(user, discord.Member) and mod_role in user.roles and reaction.emoji == search_emoji:
            check_true, tag = await self.check_for_tags(reaction.message.content)
            if check_true:
                await reaction.message.delete()
                admin_cog = self.bot.get_cog("Admin")
                if admin_cog and admin_cog.report_channel:
                    await admin_cog.report_channel.send(f"deleted message by {reaction.message.author.mention} "
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
