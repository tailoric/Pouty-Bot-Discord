from discord.ext import commands
import aiohttp
import os
import uuid
from bs4 import BeautifulSoup
class Waifu2x:
    """
    For upscaling images and removing image noise
    """

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    def __unload(self):
        self.session.close()

    @commands.command(pass_context=True)
    async def upscale(self, ctx, url=None, scale='2x', noise='medium'):
        """
        Upscale image via https://waifu2x.booru.pics
        :param scale: decide upscale factor (1x,2x)
        :param url: image url, please write 'file' instead of the url if using file upload
        :param noise: jpg-noise-reduction  (none,medium,high)
        """
        scales = ('1x', '2x')
        noises = ('none', 'low', 'medium', 'high', 'highest')
        await self.bot.type()
        if scale in scales:
            if scale == '1x':
                scale = 1
            elif scale == '2x':
                scale = 2
        else:
            scale = 2
        if noise in noises:
            if noise == 'none':
                noise = 0
            elif noise == 'medium':
                noise = 1
            elif noise == 'high':
                noise = 2
        else:
            noise = 1
        if ctx.message.attachments:
            link = ctx.message.attachments[0]['proxy_url']
        elif url:
            link = url
        else:
            await self.bot.say('need a file')
            return
        if noise == 0 and scale == 1:
            await self.bot.say("result would be source image either increase size or denoise image")
            return
        params = {'url': link, 'scale': str(scale), 'denoise': str(noise)}
        try:
            async with self.session.get('https://waifu2x.booru.pics/Home/fromlink', params=params) as response:
                if response.status == 200:
                    await self.bot.type()
                    file_url = 'https://waifu2x.booru.pics/outfiles/{}.png'
                    if 'hash' not in response.url.query.keys():
                        await self.bot.say("No image response\nfile is either too big or not an image")
                        return
                    hash_string = response.url.query['hash']
                    post_url = file_url.format(hash_string)
                    await self.bot.say(post_url)

                else:
                    message = "Response Code from waifu2x server: {} \n".format(response.status)
                    if response.status == 502:
                        message += "File probably too large \n"
                        message += "Please only upload files smaller than 5MB and 1500x1500px"
                    await self.bot.say(message)
        except Exception as e:
            print(repr(e))


def setup(bot):
    bot.add_cog(Waifu2x(bot))
