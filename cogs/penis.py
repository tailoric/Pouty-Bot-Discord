import random
from discord.ext import commands
from discord.ext.commands import Bot
import discord
from .utils.dataIO import DataIO
from .utils.checks import channel_only

class Penis(commands.Cog):
    """cog for finding the 100% accurate penis length of a user"""
    data_io = DataIO()
    allowed_channels = data_io.load_json("bot_channels")

    def __init__(self, bot:Bot):
        self.bot = bot

    @commands.command(pass_context=True)
    @channel_only(*allowed_channels)
    async def penis(self, ctx, members: commands.Greedy[discord.Member]):
        """accurately measure a user's penis size or compare the penis size of multiple users"""
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
    bot.add_cog(Penis(bot))
