from discord.ext import commands
from .utils import checks
import aiohttp
from bs4 import BeautifulSoup
import json

class Search:
    """Reverse image search commands"""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.session2 = aiohttp.ClientSession()

    def _tag_to_title(self,tag):
        return tag.replace(' ', ', ').replace('_', ' ').title()

    @commands.command(pass_context=True)
    async def source(self, ctx, link=None):
        """Search IQDB for Source of the link or uploaded image"""
        file = ctx.message.attachments
        if link is None and not file:
            await self.bot.say('Message didn\'t contain Image')
        else:
            await self.bot.type()
            if link:
                url = link
            else:
                url = file[0]['proxy_url']
            async with self.session.post(url='https://iqdb.org', data={'url': url}) as response:
                if response.status == 200:
                    soup = BeautifulSoup(await response.text(), 'html.parser')
                    # This is for the no relevant matches case
                    pages_div = soup.find(id='pages').find_all('div')[1]
                    # stop searching if no relevant match was found
                    if str(pages_div.find('th')) == '<th> No relevant matches </th>':
                        await self.bot.reply('No relevant Match was found')

                    matches = soup.find(id='pages')
                    best_match = matches.select('a')[0].attrs['href']
                    danbooru_found = False
                    for match in matches.select('a'):
                        source = match.attrs['href']
                        if source.startswith('//danbooru.donmai.us') and not danbooru_found:
                            danbooru_found = True
                            danbooru = 'http:'+source
                            characters, artist, franchise = await self._danbooru_api(danbooru)
                            message = ''
                            if characters:
                                message += '\n**Characters:** {} \n'.format(characters)
                            if artist:
                                message += '**Artist:** {} \n'.format(artist)
                            if franchise:
                                message += '**Copyright:** {} \n'.format(franchise)

                            message += '**Source:** <{}> \n'.format(danbooru)
                            await self.bot.reply(message)
                    if not danbooru_found:
                        await  self.bot.reply('<{}>'.format(best_match))

    async def _danbooru_api(self, link):
        with open('data/danbooru/danbooru.json','r') as file:
            data = json.load(file)
            user = data['user']
            api_key = data['api_key']
            auth = aiohttp.BasicAuth(user,api_key)
            characters, artist, franchise = None, None, None
            async with self.session2.get('{}.json'.format(link),auth=auth) as response:
                if response.status == 200:
                    json_dump = await response.json()
                    if json_dump['tag_count_character'] > 0:
                        characters = self._tag_to_title(json_dump['tag_string_character'])
                    if json_dump['tag_count_artist'] > 0:
                        artist = self._tag_to_title(json_dump['tag_string_artist'])
                    if json_dump['tag_count_copyright'] > 0:
                        franchise = self._tag_to_title(json_dump['tag_string_copyright'])
                    return characters, artist, franchise
                else:
                    await self.bot.reply("\n HTTP Error occured with following Status Code:{}".format(response.status))

    def __unload(self):
        self.session.close()
        self.session2.close()

def setup(bot):
    bot.add_cog(Search(bot))
