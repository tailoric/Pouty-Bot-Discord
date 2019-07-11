import discord
from discord.ext import commands
from typing import List
from .utils.dataIO import DataIO
from .utils import checks
import random


class Sword(commands.Cog):
    data_io = DataIO()
    channels = data_io.load_json("bot_channels")
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @commands.command()
    @checks.channel_only(*channels)
    async def sword(self, ctx, member: discord.Member):
        if ctx.author == member:
            await ctx.send("You take a mighty leap and your own sword plunges into your heart. Congratulations, you just played yourself.")
            return
        challenger = ctx.message.author.mention
        rival = member.mention
        battle_duration = random.randint(1, 201)
        message = f"{challenger} and {rival} dueled for {battle_duration} gruesome hours! "
        winner = random.choice([challenger, rival])
        message += f"It was a long, heated battle, but {winner} came out victorious!"
        await ctx.send(message)



def setup(bot: commands.Bot):
    bot.add_cog(Sword(bot))
