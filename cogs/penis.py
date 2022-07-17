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

    def __init__(self, bot: Bot):
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
            length_list.append(
                {"username": member.display_name, "length": length})
        for entry in length_list:
            message_string += "**{0}'s size:**\n8{1}D\n".format(
                entry["username"], "=" * entry["length"])
        await ctx.send(message_string)

    @commands.command(pass_context=True)
    @channel_only(*allowed_channels)
    async def boobs(self, ctx, width: int, user: discord.User = None):
        """accurately measures a user's cup size"""
        if not user:
            user = ctx.author
        rand = random.Random(user.id)
        size_int = rand.randint(0, 5)
        size = chr(65 + size_int)
        if size == 'E':
            size = 'DD'
        if size == 'F':
            size = 'DDD'
        boob_string = f' {"▓"*(11+(4*width))}\n'
        boob_string += f'{"▓"*(2+width)}▒{"▓"*(7+(2*width))}▒{"▓"*(2+width)}\n'
        boob_string +=  f'{"▓"*(1+width)}▒░▒{"▓"*(2+width)} {"▓"*(2+width)}▒░▒{"▓"*(1+width)}\n'
        boob_string += f'{"▓"*(2+width)}▒{"▓"*(2+width)}   {"▓"*(2+width)}▒{"▓"*(2+width)}\n'
        boob_string += f' {"▓"*(3+(2*width))}     {"▓"*(3+(2*width))}\n'
        if width >= 3:
            boob_string += f'  {"▓"*(3+(2*(width-1)))}       {"▓"*(3+(2*(width-1)))}\n'
        cup_message = f"**{user.display_name}'s tits have a cup size of __{size}__**\n"
        await ctx.send(cup_message + '```\n' + boob_string + '\n```')


async def setup(bot):
    await bot.add_cog(Penis(bot))
