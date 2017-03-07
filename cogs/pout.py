from discord.ext import commands
import random
import json


class Pout:

    def __init__(self, bot):
        self.bot = bot

    @commands.command(hidden=False)
    async def pout(self, mood="none"):
        """ Posts a cute little pout for your viewing pleasure
            usage: .pout <mood>
            only available mood is angry currently
        """
        mood_list = ('angry','sad','embarrassed')
        file_name = 'pouts'

        if mood in mood_list:
            file_name = '{}_pouts'.format(mood)
        with open('data/pouts/{}.json'.format(file_name), 'r') as f:
           data = json.load(f)
        await self.bot.say(random.choice(data))


def setup(bot):
    bot.add_cog(Pout(bot))