from discord.ext import commands
import discord
import aiohttp
from bs4 import BeautifulSoup
import json
from urllib import parse
import youtube_dl
class Search:
    """Reverse image search commands"""


    def __init__(self, bot):
        self.bot = bot
        self.iqdb_session = aiohttp.ClientSession()
        self.dans_session = aiohttp.ClientSession()
        self.sauce_session = aiohttp.ClientSession()
        self.tineye_session = aiohttp.ClientSession()

    async def _danbooru_api(self, link):
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
                await self.bot.reply("\n HTTP Error occured with following Status Code:{}".format(response.status))

    def __unload(self):
        self.iqdb_session.close()
        self.dans_session.close()
        self.sauce_session.close()
        self.tineye_session.close()


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
            await self.bot.say('Message didn\'t contain Image')
        else:
            await self.bot.type()
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
                        await self.bot.reply('No relevant Match was found')
                        return

                    matches = soup.find(id='pages')
                    best_match = matches.select('a')[0].attrs['href']
                    danbooru_found = False
                    for match in matches.select('a'):
                        source = match.attrs['href']
                        if source.startswith('//danbooru.donmai.us') and not danbooru_found:
                            danbooru_found = True
                            danbooru = 'http:'+source
                            characters, artist, franchise, source_url = await self._danbooru_api(danbooru)
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

                            await self.bot.say(embed=embed)
                    if not danbooru_found:
                        await  self.bot.reply('<{}>'.format(best_match))

    @commands.command(pass_context=True)
    async def sauce(self, ctx, link=None, similarity=80):
        """
       reverse image search via saucenao
       usage:   .sauce <image-link> <similarity (in percent)> or
                .sauce on image upload comment <similarity (in percent)>
        """
        file = ctx.message.attachments
        if link is None and not file:
            await self.bot.say('Message didn\'t contain Image')
        else:
            await self.bot.type()
            if file:
                url = file[0]['proxy_url']
                similarity = link
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
                                await self.bot.reply('<{}>'.format(source))
                                return
                    if source is None:
                        await self.bot.reply('No source over the similarity threshold')

    @commands.command(pass_context=True)
    async def tineye(self, ctx, link=None):
        """
        reverse image search using tineye
        usage:  .tineye <image-link> or
                .tineye on image upload comment
        """
        file = ctx.message.attachments
        if link is None and not file:
            await self.bot.say('Message didn\'t contain Image')
        else:
            await self.bot.type()
            if file:
                url = file[0]['proxy_url']
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
            await self.bot.reply(message)

    @commands.command()
    async def youtube(self, *, query: str):
        ytdl = youtube_dl.YoutubeDL({"quiet": True})
        info = ytdl.extract_info("ytsearch: "+ query, download=False)
        url = info["entries"][0]["webpage_url"]
        await self.bot.say(url)

    @commands.command()
    async def google(self, *, query: str):
        """give a google search link"""
        search = parse.quote_plus(query)
        await self.bot.say("https://google.com/search?q={}".format(search))


def setup(bot):
    bot.add_cog(Search(bot))
