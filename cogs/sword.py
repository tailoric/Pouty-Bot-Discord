import discord
from discord.ext import commands
from typing import List
from .utils.dataIO import DataIO
import random


class Sword(commands.Cog):
    def __init__(self, bot: commands.Bot, allowed_channels: List[int]):
        self.bot = bot
        self.allowed_channel = None
        for channel_id in allowed_channels:
            channel = bot.get_channel(channel_id)
            if channel:
                self.allowed_channel = channel
                break


    @commands.command()
    async def sword(self, ctx, member: discord.Member):
        if ctx.message.channel is not self.allowed_channel:
            await ctx.send(f"Not in the right channel, please use <#{self.allowed_channel.id}>")
            return
        challenger = ctx.message.author.mention
        rival = member.mention
        battle_duration = random.randint(1, 201)
        message = f"{challenger} and {rival} dueled for {battle_duration} gruesome hours! "
        winner = random.choice([challenger, rival])
        message += f"It was a long, heated battle, but {winner} came out victorious!"
        await ctx.send(message)



def setup(bot: commands.Bot):
    data_io = DataIO()
    channels = data_io.load_json("bot_channels")
    bot.add_cog(Sword(bot, channels))