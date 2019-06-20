import random
from discord.ext import commands
from discord.ext.commands import Bot
import discord
from .utils.dataIO import DataIO

class Penis(commands.Cog):
    """cog for finding the 100% accurate penis length of a user"""
    def __init__(self, bot:Bot, allowed_channels):
        self.bot = bot
        self.allowed_channel = None
        for channel_id in allowed_channels:
            channel = bot.get_channel(channel_id)
            if channel:
                self.allowed_channel = channel
                break

    @commands.command(pass_context=True)
    async def penis(self, ctx, members: commands.Greedy[discord.Member]):
        """accurately measure a user's penis size or compare the penis size of multiple users"""
        if ctx.message.channel != self.allowed_channel:
            await ctx.send(f"Please use the following channel: <#{self.allowed_channel.id}>")
            return
        if not members:
            members = [ctx.author]
        length_list = []
        message_string = ""
        for member in members:
            random.seed(member.id)
            length = random.randint(0, 20)
            length_list.append({"username": member.nick if member.nick else member.name, "length": length})
        for entry in length_list:
            message_string += "**{0}'s size:**\n8{1}D\n".format(entry["username"], "=" * entry["length"])
        await ctx.send(message_string)


def setup(bot):
    data_io = DataIO()
    allowed_channels = data_io.load_json("bot_channels")
    bot.add_cog(Penis(bot, allowed_channels))
