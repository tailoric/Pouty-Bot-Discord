import discord
from discord.ext import commands
import aiohttp
from textwrap import shorten
from datetime import timedelta
from html.parser import HTMLParser
import logging
import json

class MLStripper(HTMLParser):
    def __init__(self):
        self.reset()
        self.strict = False
        self.convert_charrefs= True
        self.fed = []
    def handle_data(self, d):
        self.fed.append(d)
    def get_data(self):
        return ''.join(self.fed)
        

class AniSearch(commands.Cog):
    """Commands for searching myanimelist.net"""
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.remaining_requests = None
        self.colour_converter = commands.ColourConverter()
        self.logger = logging.getLogger("PoutyBot")

    query = '''
            query ($id: Int, $search: String, $type: MediaType, $sort: [MediaSort]) {
              Media(id: $id, search: $search, type: $type, sort: $sort) {
                id
                idMal
                title {
                    userPreferred
                }
                description
                episodes
                chapters
                volumes
                status
                format
                averageScore
                externalLinks{
                    url
                }
                nextAiringEpisode {
                    episode
                    timeUntilAiring
                }
                coverImage {
                    medium
                    color
                }
              }
            }
            '''
    
    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    async def jikan_call(self, endpoint: str, parameters: dict):
        async with self.session.get(f"https://api.jikan.moe/v3/{endpoint}",
                                    params=parameters) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                return {}

    async def anilist_graphql_call(self, parameters: dict):
        async with self.session.post("https://graphql.anilist.co",
                                     json=parameters) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                print(await resp.json())
                return {}

    @commands.group(name="anilist", invoke_without_command=True)
    async def anilist(self, ctx, *, title):
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.anilist_anime, title=title)

    @anilist.error
    async def anilist_error(self, ctx, error):
        await ctx.send(error)
        self.logger.error(error, exc_info=1)

    @anilist.command(name="manga")
    async def anilist_manga(self, ctx, *, title):
        """
        for searching manga via anilist 
        """
        variables = {
            'search': title,
            'type': 'MANGA',
            'sort': ['SEARCH_MATCH', 'START_DATE_DESC', 'ID_DESC']
        }
        data = await self.anilist_graphql_call({'query': self.query,
                                                'variables': variables})
        if not data:
            return await ctx.send("Nothing found try a different query")
        embed = await self.build_anilist_manga_embed(ctx, data.get("data").get("Media"))
        await ctx.send(embed=embed)

    @anilist.command(name="anime")
    async def anilist_anime(self, ctx, *, title):
        """
        for searching anime via anilist 
        """
        variables = {
            'search': title,
            'type': 'ANIME',
            'sort': ['SEARCH_MATCH', 'START_DATE_DESC', 'ID_DESC']
        }
        data = await self.anilist_graphql_call({'query': self.query,
                                                'variables': variables})
        if not data:
            return await ctx.send("Nothing found try a different query")
        embed = await self.build_anilist_anime_embed(ctx, data.get("data").get("Media"))
        await ctx.send(embed=embed)
    @anilist.command(name="next", aliases=["episode"])
    async def anilist_next_episode(self, ctx, *, title):
        """
        get a timer for the release of the next episode of an anime via anilist
        """
        query = '''
                query ($id: Int,
                       $search: String,
                       $type: MediaType,
                       $sort: [MediaSort]) {
                  Media(id: $id, search: $search, type: $type, sort: $sort) {
                    siteUrl
                    title{
                      userPreferred
                    }
                    nextAiringEpisode{
                      timeUntilAiring
                      episode
                    }
                    coverImage{
                      color
                    }
                  }
                }
                '''
        variables = {
            'search': title,
            'type': 'ANIME',
            'sort': ['SEARCH_MATCH', 'START_DATE_DESC', 'ID_DESC']
        }
        data = await self.anilist_graphql_call({'query': query,
                                                'variables': variables})
        if not data:
            return await ctx.send("Nothing found try a different query")
        data = data.get("data").get("Media")
        anime_title = data.get("title").get("userPreferred")
        if not data.get("nextAiringEpisode"):
            return await ctx.send(f"Anime **{anime_title}** is not airing. "
                                   "Be sure you did search for the correct season.\n"
                                   "Season title must match perfectly")
        self.logger.debug(json.dumps(data, indent=2))
        cover_image_colour = data.get("coverImage").get("color")
        if cover_image_colour:
            color = await self.colour_converter.convert(ctx, cover_image_colour)
        else:
            color = discord.Colour.blurple()
        episode = data.get("nextAiringEpisode").get("episode")
        until_next = timedelta(seconds=data.get("nextAiringEpisode").get("timeUntilAiring"))
        timer_str = (f"Episode {episode} of **{anime_title}** airs in:"
                     f" {until_next}")
        embed = discord.Embed(  url=data.get("siteUrl"),
                                title=timer_str,
                                color=color
                                )
        await ctx.send(embed=embed)

    def remove_html_tags(self, text):
        if text:
            s = MLStripper()
            s.feed(text)
            return s.get_data()
        else:
            return "\u200b"

    async def build_anilist_anime_embed(self, ctx, data):
        title = data.get("title", {}).get('userPreferred', None)
        description = self.remove_html_tags(data.get("description"))
        description = shorten(description, 500, placeholder="...")
        cover_image = data.get("coverImage", None)
        embed_color = discord.Color.blurple()
        if cover_image and cover_image.get("color"):
            embed_color = await self.colour_converter.convert(ctx,
                                                              cover_image
                                                              .get("color", None))
        embed = discord.Embed(title=title,
                              description=description,
                              color=embed_color,
                              url=f"https://anilist.co/anime/{data['id']}")
        embed.set_thumbnail(url=data["coverImage"]["medium"])
        episodes = data["episodes"] if data["episodes"] else "Unknown"
        embed.add_field(name="Episodes", value=episodes)
        embed.add_field(name="Status", value=data.get("status", "\u200b").title().replace("_", " "))
        embed.add_field(name="Type", value=data["format"])
        if (score := data.get('averageScore')):
            embed.add_field(name="Score", value=f"{score}%")
        if data.get("nextAiringEpisode"):
            timer = timedelta(seconds=data["nextAiringEpisode"].get("timeUntilAiring"))
            next_episode = data["nextAiringEpisode"].get("episode")
            embed.add_field(name=f"until Episode {next_episode}:", value=f"{timer}")
        if data.get("externalLinks"):
            external_links = [l['url'] for l in data.get("externalLinks", [])[:3]]
            embed.add_field(name="External Links", value='\n'.join(external_links), inline=False)
        return embed

    async def build_anilist_manga_embed(self, ctx, data):
        colour_converter = commands.ColourConverter()
        title = data.get("title", {}).get('userPreferred', None)
        description = self.remove_html_tags(data.get("description"))
        description = shorten(description, 500, placeholder="...")
        embed_color = discord.Color.blurple()
        cover_image = data.get("coverImage", None)
        if cover_image and cover_image.get("color"):
            embed_color = await self.colour_converter.convert(ctx,
                                                              cover_image
                                                              .get("color", None))
        embed = discord.Embed(title=title,
                              description=description,
                              color=embed_color,
                              url=f"https://anilist.co/manga/{data['id']}")
        embed.set_thumbnail(url=data["coverImage"]["medium"])
        chapters = data["chapters"] if data["chapters"] else "Unknown"
        volumes = data["volumes"] if data["volumes"] else "Unknown"
        embed.add_field(name="Chapters", value=chapters)
        embed.add_field(name="Volumes", value=volumes)
        if data.get("externalLinks"):
            external_links = [l['url'] for l in data.get("externalLinks", [])[:3]]
            embed.add_field(name="External Links", value='\n'.join(external_links), inline=False)
        embed.add_field(name="Status", value=data["status"].title())
        embed.add_field(name="Type", value=data["format"].title())
        embed.add_field(name="Score", value=f"{data['averageScore']}%")
        return embed
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
    bot.add_cog(AniSearch(bot))
