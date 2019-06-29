from email.mime import base

from discord.ext import commands
import discord
import aiohttp
from bs4 import BeautifulSoup
import json
from urllib import parse
import youtube_dl
import base64
import os
import urllib.parse
import sys
from PIL import Image
import PIL
import mimetypes
import io
import asyncio


class TraceMoe:

    @staticmethod
    async def get_frame(url, session):
        mime_type = mimetypes.guess_type(url)
        if mime_type:
            if "image" in mime_type[0]:
                async with session.get(url) as response:
                    if response.status == 200:
                        return io.BytesIO(await response.read())
                    return None
            elif "video" in mime_type[0]:
                process = await asyncio.create_subprocess_exec(
                    'ffmpeg', '-y', '-i', url,
                    '-vframes', '1',
                    '-hide_banner','-loglevel', 'panic', 'data/trace/frame.jpg'
                )
                await process.communicate()
                with open('data/trace/frame.jpg', 'rb') as f:
                    return io.BytesIO(f.read())
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
            new_width = int(image.size[0] // divisor)
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
        self.iqdb_session = aiohttp.ClientSession()
        self.dans_session = aiohttp.ClientSession()
        self.sauce_session = aiohttp.ClientSession()
        self.tineye_session = aiohttp.ClientSession()
        if not os.path.exists("data/image_search"):
            os.mkdir("data/image_search/")

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
                    source = "https://www.pixiv.net/member_illust.php?mode=medium&illust_id=" + str(json_dump['pixiv_id'])
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


    def _tag_to_title(self, tag):
        return tag.replace(' ', '\n').replace('_', ' ').title()

    @commands.command(pass_context=True)
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
            await ctx.trigger_typing()
            if link:
                url = link
            else:
                url = file[0]['proxy_url']
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
                            embed = discord.Embed(colour=discord.Colour(0xa4815f), description="Source found via [iqdb](https://iqdb.org/)")

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

    @commands.command(pass_context=True)
    async def sauce(self, ctx, link=None, similarity=80):
        """
       reverse image search via saucenao
       usage:   .sauce <image-link> <similarity (in percent)> or
                .sauce on image upload comment <similarity (in percent)>
        """
        file = ctx.message.attachments
        if link is None and not file:
            await ctx.send('Message didn\'t contain Image')
        else:
            await ctx.trigger_typing()
            if file:
                url = file[0].url
                similarity = link if link is not None else similarity
            else:
                url = link
            async with self.sauce_session.get('http://saucenao.com/search.php?url={}'.format(url)) as response:
                source = None
                if response.status == 200:
                    soup = BeautifulSoup(await response.text(), 'html.parser')
                    for result in soup.select('.resulttablecontent'):
                        if float(similarity) > float(result.select('.resultsimilarityinfo')[0].contents[0][:-1]):
                            break
                        else:
                            if result.select('a'):
                                source = result.select('a')[0]['href']
                                await ctx.send('<{}>'.format(source))
                                return
                    if source is None:
                        await ctx.send('No source over the similarity threshold')

    @commands.command(pass_context=True)
    async def tineye(self, ctx, link=None):
        """
        reverse image search using tineye
        usage:  .tineye <image-link> or
                .tineye on image upload comment
        """
        file = ctx.message.attachments
        if link is None and not file:
            await ctx.send('Message didn\'t contain Image')
        else:
            await ctx.trigger_typing()
            if file:
                url = file[0].url
            else:
                url = link
            async with self.tineye_session.get('https://tineye.com/search/?url={}'.format(url)) as response:
                soup = BeautifulSoup(await response.text(), 'html.parser')
                pages = []
                image_link = None
                for hidden in soup.find(class_='match').select('.hidden-xs'):
                    if hidden.contents[0].startswith('Page:'):
                        pages.append('<{}>'.format(hidden.next_sibling['href']))
                    else:
                        image_link = hidden.a['href']
            message = '\n**Pages:** '
            message += '\n**Pages:** '.join(pages)
            if image_link is not None:
                message += '\n**direct image:** <{}>'.format(image_link)
            await ctx.send(message)

    @commands.command()
    async def youtube(self,  ctx,*, query: str):
        ytdl = youtube_dl.YoutubeDL({"quiet": True})
        info = ytdl.extract_info("ytsearch: "+ query, download=False)
        url = info["entries"][0]["webpage_url"]
        await ctx.send(url)

    @commands.command()
    async def google(self,  ctx, *, query: str):
        """give a google search link"""
        search = parse.quote_plus(query)
        await ctx.send("https://google.com/search?q={}".format(search))

    @commands.command(name="trace",aliases=["whatanime","find_anime"],pass_context=True)
    async def trace_moe(self, ctx, link: str=None):
        """search image either via link or direct upload
            example: .whatanime https://i.redd.it/y4jqyr8383o21.png"""
        if link is None and len(ctx.message.attachments) == 0:
            await ctx.send("please add an image link or invoke with an image attached")
        image_link = link if link is not None else ctx.message.attachments[0].url
        image = await TraceMoe.get_frame(image_link, self.sauce_session)
        if image:
            im = Image.open(image)
            header = {"Content-Type": "application/json"}
            request_data = {"image": TraceMoe.scale_image_down(im)}
            async with self.sauce_session.post(json=request_data, headers=header, url="https://trace.moe/api/search") as resp:
                if resp.status == 200:
                    resp_json = await resp.json()
                    first_result = resp_json["docs"][0]
                    if first_result["similarity"] > 0.85:
                        embed = self.build_embed_for_trace_moe(first_result)
                        await ctx.send(embed=embed)
                    else:
                        await ctx.send("Nothing found, refer to the FAQ to see what the cause could be:\n"
                                       "https://trace.moe/faq")
                elif resp.status == 429:
                    await ctx.send(await resp.read())
                elif resp.status == 413:
                    await ctx.send("Image to big please scale it down")
                if resp.status == 500 or resp.status == 503:
                    await ctx.send("Internal server error at trace.moe")

    def scale_down_image(self, image):
        img = Image.open(io.BytesIO(image))
        new_width = img.size[0] // 2
        wpercent = (new_width / float(img.size[0]))
        new_height = int(float(img.size[1])* float(wpercent))
        img = img.resize((new_width, new_height), Image.ANTIALIAS)
        img_save = io.BytesIO()
        img.save(img_save, format('PNG'))
        return base64.b64encode(img_save.getvalue())

    def build_embed_for_trace_moe(self, first_result):
        embed = discord.Embed(colour=discord.Colour(0xa4815f), description="Source found via [trace.moe](https://trace.moe/)")
        if not first_result["is_adult"]:
            embed.set_thumbnail(url="https://trace.moe/thumbnail.php?anilist_id={0}&file={1}&t={2}&token={3}"
                            .format(first_result["anilist_id"], urllib.parse.quote(first_result["filename"]), first_result["at"], first_result["tokenthumb"]))
        embed.add_field(name="Name", value=first_result["title_romaji"])
        m, s = divmod(first_result["at"], 60)
        embed.add_field(name="Episode {0}".format(first_result["episode"]), value="at {0:02d}:{1:02d}".format( int(m), int(s)))
        embed.add_field(name="MAL", value=self.build_mal_link_from_id(first_result["mal_id"]))
        embed.add_field(name="anilist", value=self.build_anilist_link_from_id(first_result["anilist_id"]))
        return embed

    def build_mal_link_from_id(self, id):
        return "https://myanimelist.net/anime/" + str(id)


    def build_anilist_link_from_id(self, id):
        return "https://anilist.co/anime/" + str(id)
def setup(bot):
    bot.add_cog(Search(bot))
