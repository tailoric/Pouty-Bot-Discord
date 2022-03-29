from datetime import timedelta, timezone, datetime
import random
from discord.ext import commands, tasks
import discord

class April(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.colours = [
                    discord.Colour(0xd2aee6),
                    discord.Colour(0xc2d595),
                    discord.Colour(0xd3d4a4),
                    discord.Colour(0xDEC092),
                    discord.Colour(0x9e9cb0),
                    discord.Colour(0xa9d0d9),
                    discord.Colour(0xF3AAAC),
                    discord.Colour(0xAAEAAC),
                    discord.Colour(0xAD5CDD),
                    discord.Colour(0xAFCE66),
                    discord.Colour(0xE5E443),
                    discord.Colour(0x964797),
                    discord.Colour(0x6CB2C3),
                    discord.Colour(0xCF2026),
                    discord.Colour(0x59EE5E),
                ]
        guild = bot.get_guild(187423852224053248)
        if guild:
            self.role = guild.get_role(189594836687519744)
        else: 
            test_guild = bot.get_guild(287695136840876032)
            self.role = test_guild.get_role(514884001417134110)
        self.shuffled = self.colours.copy()
        random.shuffle(self.shuffled)
        super().__init__()


    async def cog_load(self):
        self.change_memester.start()


    async def cog_unload(self):
        self.change_memester.cancel()

    @tasks.loop(hours=1)
    async def change_memester(self):
        if not self.shuffled:
            self.shuffled = self.colours.copy()
            random.shuffle(self.shuffled)
        await self.role.edit(colour=self.shuffled.pop())
        minutes = 60 + (random.randint(0, 30) * random.choice([1,-1]))
        self.change_memester.change_interval(minutes=minutes)


async def setup(bot: commands.Bot):
    await bot.add_cog(April(bot))
