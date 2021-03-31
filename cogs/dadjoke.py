import re
import time
from discord.ext import commands
from aiohttp import ClientSession
import random
class Dadjoke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = ClientSession()

    @commands.Cog.listener("on_command_completion")
    async def dad_joke(self, ctx):
        chance = random.randint(0, 100)
        joke_prefixes = [
                "Stop me if you heard this one before: ",
                "Here comes a real kneeslapper: ",
                "I just remembered a real funny one: "
                ]
        headers= {
                "Accept": "application/json",
                "User-Agent": "Pouty Bot Discord Bot (https://github.com/tailoric/Pouty-Bot-Discord/)"
            }
        if chance < 25:
            async with self.session.get("https://icanhazdadjoke.com/", headers=headers) as response:
                if response.status < 400:
                    joke_response = await response.json()
                    joke = "\n".join([random.choice(joke_prefixes), joke_response.get("joke")])
                    await ctx.send(joke)
    
    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

def setup(bot):
    bot.add_cog(Dadjoke(bot))
