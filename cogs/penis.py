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
            rand = random.Random(member.id)
            length = rand.randint(0, 20)
            length_list.append({"username": member.display_name, "length": length})
        for entry in length_list:
            message_string += "**{0}'s size:**\n8{1}D\n".format(entry["username"], "=" * entry["length"])
        await ctx.send(message_string)

class Boobs(commands.Cog):
    """cog for finding the cup size of a user"""
    data_io = DataIO()
    allowed_channels = data_io.load_json("bot_channels")

    def __init__(self, bot:Bot):
        self.bot = bot
    
    @commands.command(pass_context=True)
    @channel_only(*allowed_channels)
    async def boobs(self, ctx, user: discord.User = None):
        """accurately measure a user's penis size or compare the penis size of multiple users"""
        if not user:
            user = ctx.author
        boob_string = ' *       *       *\n*       * *       *\n*  o   *   *   o  *\n * * *       * * * \n'
        rand = random.Random(user.id)
        """Boob size"""
        height = rand.randint(0, 5)
        size = chr(65 + height)
        if size == 'E':
            size = 'DD'
        if size == 'F':
            size = 'DDD'
        for i in range(height):
            boob_string = f'{"*": >{i+3}}{"*": >{15-(i*2)-1}}\n' + boob_string
        cup_message = f"**User {user.display_name}'s tits have a cup size of __{size}__**\n"
        await ctx.send(cup_message + '```\n' + boob_string + '\n```')


async def setup(bot):
    await bot.add_cog(Penis(bot))
    await bot.add_cog(Boobs(bot))
