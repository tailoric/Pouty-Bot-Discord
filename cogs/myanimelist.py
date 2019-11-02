import discord
from discord.ext import commands
import aiohttp
class MyAnimeList(commands.Cog):
    """Commands for searching myanimelist.net"""
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.remaining_requests = None

    async def jikan_call(self, endpoint: str, parameters: dict):
        async with self.session.get(f"https://api.jikan.moe/v3/{endpoint}", params=parameters) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                return {}

    @commands.cooldown(30,60,commands.BucketType.default)
    @commands.group(name="mal", invoke_without_command=True)
    async def mal_search(self, ctx, *, title):
        """
        main command for searching myanimelist for anime, if no subcommand (manga or anime) used then
        it uses the anime search.
        """
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.mal_anime, title=title)

    @mal_search.command(name="anime")
    async def mal_anime(self, ctx, *, title):
        """searches myanimelist.net for an anime with certain title"""
        response = await self.jikan_call("search/anime", {"q": title, "page": 1})
        for result in response.get("results", []):
            if result["title"].lower() == title.lower():
                embed = self.build_mal_embed_anime(result)
                await ctx.send(embed=embed)
                return
        if len(response.get("results", [])) < 1:
            await ctx.send("Series not found check if you have written it correctly")
        else:
            embed = self.build_mal_embed_anime(response.get("results")[0])
            await ctx.send(embed=embed)

    @mal_search.command(name="manga")
    async def mal_manga(self, ctx, *, title):
        """search myanimelist for a manga with a certain title"""
        response = await self.jikan_call("search/manga", {"q": title, "page": 1})
        for result in response.get("results", []):
            if result["title"].lower() == title.lower():
                embed = self.build_mal_embed_manga(result)
                await ctx.send(embed=embed)
                return
        if len(response.get("results", [])) < 1:
            await ctx.send("Series not found check if you have written it correctly")
        else:
            embed = self.build_mal_embed_manga(response.get("results")[0])
            await ctx.send(embed=embed)

    def build_mal_embed_anime(self, result):
        embed = discord.Embed(title=result["title"], description=result["synopsis"], url=result["url"],
                              color=0x2e51a2)
        embed.add_field(name="Episodes", value=result["episodes"])
        embed.add_field(name="Status", value="Airing" if result["airing"] else "Completed")
        embed.add_field(name="Type", value=result["type"])
        embed.add_field(name="Score", value=result["score"])
        embed.set_thumbnail(url=result["image_url"])
        return embed

    def build_mal_embed_manga(self, result):
        embed = discord.Embed(title=result["title"], description=result["synopsis"], url=result["url"],
                              color=0x2e51a2)
        embed.add_field(name="Chapters", value=result["chapters"] if result["chapters"] > 0 else "Unknown")
        embed.add_field(name="Volumes", value=result["volumes"] if result["volumes"] > 0 else "Unknown")
        embed.add_field(name="Status", value="Publishing" if result["publishing"] else "Completed")
        embed.add_field(name="Type", value=result["type"])
        embed.add_field(name="Score", value=result["score"])
        embed.set_thumbnail(url=result["image_url"])
        return embed

def setup(bot):
    bot.add_cog(MyAnimeList(bot))