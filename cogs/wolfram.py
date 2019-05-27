import aiohttp
from discord.ext import commands
import json
from bs4 import BeautifulSoup
from urllib import parse


class Wolfram(commands.Cog):
    """Wolfram Alpha related commands"""

    def __init__(self, bot):
        self.bot = bot
        self.json_file = 'data/wolfram.json'
        self.session = aiohttp.ClientSession()

    @commands.command()
    async def wolfram(self,  ctx, *, query: str):
        """
        gives a wolfram query result
        :param query: the query you want to search use 'image' as first keywoard to get your result as image
        """
        with open(self.json_file) as f:
            api_key = json.load(f)['api_key']

        url = 'http://api.wolframalpha.com/v2/query'
        want_image = query.split(' ')[0] == 'image'
        if not want_image:
            params = {'appid': api_key, 'input': query, 'format': 'plaintext'}
            async with ctx.typing():
                async with self.session.get(url=url, params=params) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        success = soup.find('queryresult')['success']
                        if success == 'true':
                            query_input = soup.find('plaintext').contents
                            full_response = '<http://www.wolframalpha.com/input/?i={}>'.format(parse.quote_plus(query))
                            message = '**Full Response:** {} \n'.format(full_response)
                            message += '**Input:** {} \n'.format(query_input[0])
                            message += '**Result:** \n' \
                                       '```\n'
                            for elem in soup.find_all('plaintext')[1:6]:
                                if len(elem) > 0:
                                    message += elem.contents[0] + '\n'
                            message += '```'

                            await ctx.send(message)
                        else:
                            await ctx.send('Query was unsuccessful please try something else')
        else:
            re_query = query.split(' ')[1:]
            re_query = ' '.join(re_query)
            params = {'appid': api_key, 'input': re_query, 'format': 'plaintext,image'}
            async with ctx.typing():
                async with self.session.get(url=url, params=params) as response:
                    if response.status == 200:
                        soup = BeautifulSoup(await response.text(), 'html.parser')
                        success = soup.find('queryresult')['success']
                        if success == 'true':
                            query_input = soup.find('plaintext').contents
                            full_response = '<http://www.wolframalpha.com/input/?i={}>'.format(parse.quote_plus(re_query))
                            message = '**Full Response:** {} \n'.format(full_response)
                            message += '**Input:** {} \n'.format(query_input[0])
                            message += '**Result:** \n'
                            await ctx.send(message)
                            for elem in soup.find_all('img')[1:5]:
                                await ctx.send(elem['src'])
                        else:
                            await ctx.send('Query was unsuccessful please try something else')

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())


def setup(bot):
    bot.add_cog(Wolfram(bot))
