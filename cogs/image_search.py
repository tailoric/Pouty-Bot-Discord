from datetime import datetime, timezone
from PIL import Image
from bs4 import BeautifulSoup
from discord.ext import commands
from email.mime import base
from pathlib import Path
from urllib import parse
from .utils.converters import SimpleUrlArg

import aiohttp
import asyncio
import base64
import discord
import io
import json
import logging
import mimetypes
import sys
import typing
import urllib.parse
import yt_dlp


class SauceNaoResult:
    def __init__(self, result):
        self.header = result['header']
        self.data = result['data']
        self.similarity = float(self.header.get('similarity'))
        self.source_url = self.data.get('ext_urls')
        self.title = self.data.get('source')
        self.thumbnail = self.header.get('thumbnail')
        self.est_time = None
        self.is_anime = False
        self.is_manga = False
        if self.header['index_id'] == 37:
            self.is_manga = True
            self.chapter = self.data.get('part')
            self.chapter = self.chapter[self.chapter.find('Chapter')+8:]
            self.artist = self.data.get('artist')
            self.author = self.data.get('author')
        elif self.header['index_id'] == 21:
            self.is_anime = True
            self.est_time = self.data.get('est_time')
            self.episode = self.data.get('part')
            self.year = self.data.get('year')
            self.year = self.data.get('year')
        else:
            self.source_url = self.data.get('source')
            if self.source_url is None:
                self.title = self.data.get('ext_urls')[0]

    def get(self, property_name, default=u'\u200b'):
        attribute = getattr(self, property_name)
        if attribute:
            return attribute
        else:
            return default

class TraceMoe:

    anilist_query = """
        query($id:Int){
          Media(id: $id) {
            title {
              userPreferred
            }
            description
            coverImage{
              color
            }
            nextAiringEpisode {
              airingAt
              episode
            }
          }
        }
    """
    @staticmethod
    async def get_frame(url, session):
        mime_type = mimetypes.guess_type(url)
        if any(mime_type) and mime_type:
            if "image" in mime_type[0]:
                async with session.get(url) as response:
                    if response.status == 200:
                        return io.BytesIO(await response.read())
                    return None
            return None

    @staticmethod
    def scale_image_down(image):
        img = io.BytesIO()
        image.save(img, format(image.format))
        im_size = sys.getsizeof(img.getvalue())
        max_size = 1* 10 ** 6
        if image.format == 'GIF' and image.is_animated:
            image_save = io.BytesIO()
            image.save(image_save, format("PNG"), save_all=False)
            return base64.b64encode(image_save.getvalue()).decode('ascii')
        elif im_size > max_size:
            divisor = im_size / max_size
            new_width = int(image.size[0] // 2)
            wpercent = (new_width / float(image.size[0]))
            new_height = int(float(image.size[1]) * float(wpercent))
            img = image.resize((new_width, new_height), Image.ANTIALIAS)
            img_save = io.BytesIO()
            img.save(img_save, format('PNG'))
            return base64.b64encode(img_save.getvalue()).decode('ascii')
        return base64.b64encode(img.getvalue()).decode('ascii')


class Search(commands.Cog):
    """Reverse image search commands"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('PoutyBot')
        self.iqdb_session = aiohttp.ClientSession()
        self.dans_session = aiohttp.ClientSession()
        self.sauce_session = aiohttp.ClientSession()
        self.tineye_session = aiohttp.ClientSession()
        self.sauce_nao_settings = Path('config/sauce_nao_settings.json')
        if not self.sauce_nao_settings.exists():
            self.sauce_nao_settings.touch()
            self.sauce_nao_settings = {}
        with self.sauce_nao_settings.open('r') as f:
            self.sauce_nao_settings = json.load(f)
        self.sauce_nao_settings['long_remaining'] = 200
        self.sauce_nao_settings['short_remaining'] = 6
        self.reset_time_tasks = []
    async def _danbooru_api(self, ctx, link):
        """
        looks up information about the image on danbooru
        :param link: must be a valid danbooru link
        :return: characters, artist, copyright (franchise)
        """

        # json file with api key and user name for danbooru
        # Structure:
        # {
        #  "user": "username",
        #  "api_key": "ValidApiKey123"
        # }
        auth_file_path = 'data/danbooru/danbooru.json'
        with open(auth_file_path, 'r') as file:
            data = json.load(file)
            user = data['user']
            api_key = data['api_key']
        auth = aiohttp.BasicAuth(user, api_key)
        characters, artist, franchise, source = None, None, None, None
        async with self.dans_session.get('{}.json'.format(link), auth=auth) as response:
            if response.status == 200:
                json_dump = await response.json()
                if json_dump['tag_count_character'] > 0:
                    characters = self._tag_to_title(json_dump['tag_string_character'])
                if json_dump['tag_count_artist'] > 0:
                    artist = self._tag_to_title(json_dump['tag_string_artist'])
                if json_dump['tag_count_copyright'] > 0:
                    franchise = self._tag_to_title(json_dump['tag_string_copyright'])
                if json_dump['pixiv_id']:
                    source = "https://www.pixiv.net/member_illust.php?mode=medium&illust_id=" + str(
                        json_dump['pixiv_id'])
                elif json_dump['source']:
                    source = json_dump['source']
                return characters, artist, franchise, source
            else:
                await ctx.send("\n HTTP Error occured with following Status Code:{}".format(response.status))

    def cog_unload(self):
        loop = self.bot.loop or asyncio.get_event_loop()
        loop.create_task(self.iqdb_session.close())
        loop.create_task(self.dans_session.close())
        loop.create_task(self.sauce_session.close())
        loop.create_task(self.tineye_session.close())
        for task in self.reset_time_tasks:
            task.cancel()


    def _tag_to_title(self, tag):
        return tag.replace(' ', '\n').replace('_', ' ').title()

    @commands.command()
    async def iqdb(self, ctx, link=None):
        """Search IQDB for source of an image on danbooru
        if no danbooru link is found it returns the best match
        usage:  .iqdb <link> or
                .iqdb on image upload comment
        """
        file = ctx.message.attachments
        if link is None and not file:
            await ctx.send('Message didn\'t contain Image')
        else:
            try:
                await ctx.typing()
            except:
                self.logger.exception("error during typing")
            if link:
                url = link
            else:
                url = file[0].url
            url = url.strip("<>|")
            async with self.iqdb_session.post(url='https://iqdb.org', data={'url': url}) as response:
                if response.status == 200:
                    soup = BeautifulSoup(await response.text(), 'html.parser')
                    # This is for the no relevant matches case
                    pages_div = soup.find(id='pages').find_all('div')[1]
                    # stop searching if no relevant match was found
                    if str(pages_div.find('th')) == '<th>No relevant matches</th>':
                        await ctx.send('No relevant Match was found')
                        return

                    matches = soup.find(id='pages')
                    best_match = matches.select('a')[0].attrs['href']
                    danbooru_found = False
                    for match in matches.select('a'):
                        source = match.attrs['href']
                        if source.startswith('//danbooru.donmai.us') and not danbooru_found:
                            danbooru_found = True
                            danbooru = 'http:'+source
                            characters, artist, franchise, source_url = await self._danbooru_api(ctx, danbooru)
                            embed = discord.Embed(colour=discord.Colour(0xa4815f), description=f"Source found via [iqdb](https://iqdb.org/?url={url})")

                            embed.set_thumbnail(url=url)

                            if characters:
                                embed.add_field(name="Character", value=characters)
                            if artist or source_url:
                                if source_url and artist:
                                    embed.add_field(name="Artist", value="[{}]({})".format(artist, source_url))
                                elif artist:
                                    embed.add_field(name="Artist", value=artist)
                                else:
                                    embed.add_field(name="Source", value=source_url)

                            if franchise:
                                embed.add_field(name="Copyright", value=franchise)
                            embed.add_field(name="Danbooru", value=danbooru)

                            await ctx.send(embed=embed)
                    if not danbooru_found:
                        await ctx.send('<{}>'.format(best_match))

    async def reset_long_limit(self):
        await asyncio.sleep(86400)
        self.sauce_nao_settings["long_remaining"] = 200

    async def reset_short_limit(self):
        await asyncio.sleep(30)
        self.sauce_nao_settings["short_remaining"] = 6

    @commands.command(aliases=["source","saucenao"])
    async def sauce(self, ctx, link: typing.Optional[SimpleUrlArg], similarity=80):
        """
       reverse image search via saucenao
       usage:   .sauce <image-link> <similarity (in percent)> or
                .sauce on image upload comment <similarity (in percent)>
        """
        file = ctx.message.attachments
        if not link and not file and ctx.message.reference:
            link = self.get_referenced_message_image(ctx)
        if link is None and not file:
            await ctx.send('Message didn\'t contain Image')
        if self.sauce_nao_settings.get("short_remaining") == 0:
            return await ctx.send("Ratelimit reached. Please wait 30 seconds before doing another search")
        if self.sauce_nao_settings.get("long_remaining") == 0:
            return await ctx.send("No more searches available for today. Please wait 24 hours before doing another search")
        else:
            try:
                await ctx.typing()
            except:
                self.logger.exception("exception during typing")
            if file:
                url = file[0].url
                similarity = link if link is not None else similarity
            else:
                url = link
            url = url.strip("<>|")
            saucenao_url = 'https://saucenao.com/search.php'
            search_url = '{}?url={}'.format(saucenao_url,url)
            params = {
                    'url': url,
                    'output_type': 2,
                    'api_key': self.sauce_nao_settings.get('api_key'),
                    'hide': 2
                    }
            async with self.sauce_session.get(url=saucenao_url, params=params) as response:
                source = None
                if response.status == 200:
                    resp = await response.json()
                    header = resp['header']
                    results = resp['results']
                    self.sauce_nao_settings['short_remaining'] = header['short_remaining']
                    self.sauce_nao_settings['long_remaining'] = header['long_remaining']
                    if self.sauce_nao_settings.get("short_remaining") == 0:
                        self.reset_time_tasks.append(self.bot.loop.create_task(self.reset_short_limit()))
                    if self.sauce_nao_settings.get("long_remaining") == 0:
                        self.reset_time_tasks.append(self.bot.loop.create_task(self.reset_long_limit()))
                    for result in results:
                        if float(similarity) > float(result['header']['similarity']):
                            break
                        else:
                            sn_result = SauceNaoResult(result)
                            embed = discord.Embed(title=sn_result.title, description=f"Source found via [saucenao]({search_url})")
                            if sn_result.source_url and sn_result.source_url[0].startswith(("http:", "https:")):
                                embed.url = sn_result.source_url[0]
                            if sn_result.thumbnail:
                                embed.set_thumbnail(url=sn_result.thumbnail)
                            if sn_result.is_anime:
                                embed.add_field(name="Episode", value=sn_result.get('episode'))
                                embed.add_field(name="Est. Time", value=sn_result.get('est_time'))
                                embed.add_field(name="Year", value=sn_result.get('year'))
                            if sn_result.is_manga:
                                embed.add_field(name="Chapter", value=sn_result.get('chapter'))
                                embed.add_field(name="Author", value=sn_result.get('author'))
                                embed.add_field(name="Artist", value=sn_result.get('artist'))
                            return await ctx.send(embed=embed)
                    if source is None:
                        await ctx.send('No source over the similarity threshold')
                else:
                    info = await response.json()
                    paginator = commands.Paginator()
                    paginator.add_line(f"Error when calling saucenao (HTTP STATUS: {response.status}):", empty=True)
                    for line in json.dumps(info, indent=4).splitlines():
                        paginator.add_line(line)
                    for page in paginator.pages:
                        await ctx.send(page)

    @commands.command()
    async def yt_version(self, ctx):
        await ctx.send(youtube_dl.version.__version__)
    @commands.command(aliases=["y",'yt'])
    async def youtube(self,  ctx,*, query: str):
        try:
            ytdl = yt_dlp.YoutubeDL({"quiet": True})
            async with ctx.typing():
                info = ytdl.extract_info("ytsearch: " + query, download=False)
                url = info["entries"][0]["webpage_url"]
            await ctx.send(url)
        except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as yt_error:
            self.logger.error(yt_error, exc_info=1)
            await ctx.send("Youtube dl seems to be outdated please call `update_ytdl`, "
                           "if that doesn't fix the problem change your search or contact the bot owner")
        except Exception as e:
            await ctx.send(f"Command exited with error: ```\n{e}\n```")
            self.logger.error(e, exc_info=1)

    
    @commands.command(name="update_ytdl")
    async def update_ytdl(self, ctx):
        async with ctx.typing():
            try: 
                proc = await asyncio.create_subprocess_exec(
                        sys.executable, '-m', 'pip', 'install', '-U', 'yt_dlp'
                        )
                await proc.communicate()
                await ctx.send("update completed")
                keys = sys.modules.copy().keys()
                for key in keys:
                    if type(key) is str and key.startswith('yt_dlp'):
                        del sys.modules[key]

                self.bot.reload_extension('cogs.image_search')
            except Exception as e:
                self.logger.error(e, exc_info=1)
                raise e

    @commands.command()
    async def google(self,  ctx, *, query: str):
        """give a google search link"""
        search = parse.quote_plus(query)
        await ctx.send("https://google.com/search?q={}".format(search))
    @commands.command()
    async def lmgtfy(self,  ctx, *, query: str):
        """give a let me google that for you link"""
        search = parse.quote_plus(query)
        await ctx.send("<https://lmgtfy.com/?q={}>".format(search))

    def get_referenced_message_image(self, ctx):
        link = None
        if ctx.message.reference and ctx.message.reference.resolved:
            if ctx.message.reference.resolved.attachments:
                link = ctx.message.reference.resolved.attachments[0].url
            else:
                link = ctx.message.reference.resolved.embeds[0].url
        return link

    @commands.command(name="trace", aliases=["whatanime", "find_anime"])
    @commands.cooldown(rate=2,per=60,type=commands.BucketType.user)
    async def trace_moe(self, ctx, similarity: typing.Optional[int] = 85,link: typing.Optional[str] = None):
        """search image either via link or direct upload
            example: .whatanime https://i.redd.it/y4jqyr8383o21.png"""
        try:
            await ctx.typing()
        except:
            self.logger.exception("error during typing")
        if similarity < 1 or similarity > 99:
            await ctx.send("similarity must be between 1 or 99 percent")
            return
        if link is None and not ctx.message.attachments:
            link = self.get_referenced_message_image(ctx)
        if link is None and len(ctx.message.attachments) == 0:
            await ctx.send("please add an image link or invoke with an image attached")
            return
        image_link = link if link is not None else ctx.message.attachments[0].url
        image_link = image_link.strip("<>|")
        image = await TraceMoe.get_frame(image_link, self.sauce_session)
        if image:
            request_data = {"image": image}
            async with self.sauce_session.post(data=request_data, url="https://api.trace.moe/search", raise_for_status=True) as resp:
                if resp.status == 200:
                    resp_json = await resp.json()
                    sorted_found = sorted(resp_json["result"], key=lambda d: d['similarity'], reverse=True)
                    first_result = sorted_found[0]
                    threshold = similarity / 100
                    if first_result["similarity"] >= threshold:
                        embed = await self.build_embed_for_trace_moe(first_result)
                        await ctx.send(embed=embed)
                    else:
                        await ctx.send("Nothing found, refer to the FAQ to see what the cause could be:\n"
                                       "https://trace.moe/faq")
                elif resp.status == 429:
                    await ctx.send(await resp.read())
                elif resp.status == 413:
                    await ctx.send("Image too big please scale it down")
                if resp.status == 500 or resp.status == 503:
                    await ctx.send("Internal server error at trace.moe")
        else:
            await ctx.send("Could not detect filetype, be sure to use actual media files"
                           "\n(for imgur please use the .gif instead of gifv)")


    @trace_moe.error
    async def trace_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(error)
        else:
            await ctx.send(error)

    async def build_embed_for_trace_moe(self, first_result):
        anilist_url = None
        title = None
        data = None
        print(first_result)
        if first_result.get('anilist'):
            anilist_url = f"https://anilist.co/anime/{first_result.get('anilist')}"
            async with self.sauce_session.post(url="https://graphql.anilist.co", json={"query": TraceMoe.anilist_query, "variables": {'id': first_result.get('anilist')}}) as resp:
                if resp.status < 400:
                    anilist_data = await resp.json()
                    data = anilist_data.get("data")
                    title = data.get("Media", {}).get("title", {}).get("userPreferred", None)

        embed = discord.Embed(title=title or first_result.get("filename"), url=anilist_url or None)
        start_min, start_seconds = divmod(int(first_result.get('from')), 60)
        start_hours, start_min = divmod(start_min, 60)
        embed.add_field(name=f"Episode {first_result.get('episode')}", value=f"At {start_hours:02d}:{start_min:02d}:{start_seconds:02d}", inline=False)
        embed.add_field(name="Similarity", value=f"{round(first_result.get('similarity'), 3) * 100:.1f}%", inline=False)
        if data and data.get("Media", {}).get("nextAiringEpisode"):
            next_ep = data.get("Media", {}).get("nextAiringEpisode", {})
            embed.add_field(name="Next Episode", value=f"EP {next_ep.get('episode')} on <t:{next_ep.get('airingAt')}>")
        if data and data.get("Media", {}).get("coverImage"):
            color = data.get("Media", {}).get("coverImage", {}).get("color")
            if color:
                val = int(color.strip("#"), 16)
                embed.color = discord.Colour(val)
        embed.set_thumbnail(url=first_result.get("image", None))
        return embed

    def build_mal_link_from_id(self, id):
        return "https://myanimelist.net/anime/" + str(id)

    def build_anilist_link_from_id(self, id):
        return "https://anilist.co/anime/" + str(id)


async def setup(bot):
    await bot.add_cog(Search(bot))
