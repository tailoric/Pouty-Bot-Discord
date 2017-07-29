from discord.ext import commands
import aiohttp
import json
class Danbooru:

    def __init__(self, bot):
        self.bot = bot
        self.danbooru_session = aiohttp.ClientSession()
        self.auth_file = 'data/danbooru/danbooru.json'



    @commands.command()
    async def dan(self,*,tags:str):
        """
        look for the most recent image on danbooru with specified tags
        """
        params = {'tags' : tags, 'limit' : '1'}
        with open(self.auth_file, 'r') as file:
            data = json.load(file)
            user = data['user']
            api_key = data['api_key']
        auth = aiohttp.BasicAuth(user, api_key)
        url = 'http://danbooru.donmai.us/'
        async with self.danbooru_session.get('{}posts.json'.format(url),params=params,auth=auth) as response:
            if response.status == 200:
                json_dump = await response.json()
                if json_dump:
                    await self.bot.say(url + json_dump[0]['file_url'])
                else:
                    await self.bot.say('empty Server response')
            else:
                await self.bot.say('Danbooru server answered with error code:\n```\n{}\n```'.format(response.status))

    @commands.command()
    async def danr(self,*,tags:str):
        """
        look for a random image on danbooru with specified tags
        """
        params = {'tags' : tags, 'limit' : '1','random' : 'true'}
        with open(self.auth_file, 'r') as file:
            data = json.load(file)
            user = data['user']
            api_key = data['api_key']
        auth = aiohttp.BasicAuth(user, api_key)
        url = 'http://danbooru.donmai.us/'
        async with self.danbooru_session.get('{}posts.json'.format(url),params=params,auth=auth) as response:
            if response.status == 200:
                json_dump = await response.json()
                if json_dump:
                    await self.bot.say(url + json_dump[0]['file_url'])
                else:
                    await self.bot.say('empty Server response')
            else:
                await self.bot.say('Danbooru server answered with error code:\n```\n{}\n```'.format(response.status))

def setup(bot):
    bot.add_cog(Danbooru(bot))
