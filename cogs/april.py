from datetime import timedelta, timezone, datetime
import random
from discord.ext import commands, tasks
import discord
import re
import random

from discord.mentions import AllowedMentions


class April(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.excluded_channels = [
            366659034410909717,
            463597797342445578,
            426174461637689344,
            363758396698263563,
            595585060909088774,
        ]

    @commands.Cog.listener("on_message")
    async def huga(self, message: discord.Message):
        if (
            message.guild
            and message.channel.id not in self.excluded_channels
            and random.random() <= 0.001
        ):
            await message.channel.send("huga_!_")
        if (
            message.guild
            and not message.author.bot
            and 'huga' in message.content
            and random.random() <= 0.1
        ):
            await message.channel.send("huga!!")


async def setup(bot: commands.Bot):
    await bot.add_cog(April(bot))
