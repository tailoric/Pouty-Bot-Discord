from discord.ext import commands
import json
import re
import os
from .utils.checks import is_owner_or_moderator

class Filter(commands.Cog):
    """
    filters messages and removes them
    """

    def __init__(self, bot,):
        self.bot = bot
        self.filter_file_path = "data/filter.json"

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

    async def on_message(self, message):
        contains_giphy_or_tenor_link_regex = re.compile("https://(media\.)?(tenor|giphy)?.com/")
        match = contains_giphy_or_tenor_link_regex.match(message.content)
        if match and not message.channel == self.allowed_channel:
            await self.bot.delete_message(message)

    @is_owner_or_moderator()
    @commands.command(name="filter_exception", pass_context=True)
    async def setup_exception_channel(self,  ctxctx):
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
