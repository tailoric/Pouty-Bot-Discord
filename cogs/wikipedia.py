import wikipedia

from discord.ext import commands

class Wikipedia(commands.Cog):
    def __init__(self,bot):
        self.bot = bot

    @commands.command()
    async def wiki(self,  ctx, *, query):
        params = {
                "action": "opensearch",
                "namespace": "0",
                "search": query,
                "limit": "1",
                "format": "json"
                }
        async with self.bot.session.get("https://en.wikipedia.org/w/api.php", params=params, raise_for_status=True) as resp:
            data = await resp.json()
            if len(data) == 4 and data[3]:
                await ctx.send(data[3][0])
            else:
                return await ctx.send("Nothing found")


async def setup(bot):
    await bot.add_cog(Wikipedia(bot))

