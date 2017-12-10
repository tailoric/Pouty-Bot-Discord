import wikipedia

from discord.ext import commands

class Wikipedia:

    def __init__(self,bot):
        self.bot = bot

    @commands.command()
    async def wiki(self, *, query):
        res = wikipedia.search(query)
        try:
            link = wikipedia.page(res[0]).url
        except wikipedia.exceptions.DisambiguationError as e:
            link = wikipedia.page(e.options[0]).url
        await self.bot.say(link)


def setup(bot):
    bot.add_cog(Wikipedia(bot))

