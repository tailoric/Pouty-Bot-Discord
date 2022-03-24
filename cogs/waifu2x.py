from discord.ext import commands
import aiohttp
class Waifu2x(commands.Cog):
    """
    For upscaling images and removing image noise
    """

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    @commands.command(pass_context=True)
    async def upscale(self,  ctxctx, url=None, scale='2x', noise='medium'):
        """
        Upscale image via https://waifu2x.booru.pics
        :param scale: decide upscale factor (1x,2x)
        :param url: image url, please write 'file' instead of the url if using file upload
        :param noise: jpg-noise-reduction  (none,medium,high)
        """
        scales = ('1x', '2x')
        noises = ('none', 'low', 'medium', 'high', 'highest')
        await ctx.typing()
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
            await ctx.send('need a file')
            return
        if noise == 0 and scale == 1:
            await ctx.send("result would be source image either increase size or denoise image")
            return
        params = {'url': link, 'scale': str(scale), 'denoise': str(noise)}
        try:
            async with self.session.get('https://waifu2x.booru.pics/Home/fromlink', params=params) as response:
                if response.status == 200:
                    await ctx.typing()
                    file_url = 'https://waifu2x.booru.pics/outfiles/{}.png'
                    if 'hash' not in response.url.query.keys():
                        await ctx.send("No image response\nfile is either too big or not an image")
                        return
                    hash_string = response.url.query['hash']
                    post_url = file_url.format(hash_string)
                    await ctx.send(post_url)

                else:
                    message = "Response Code from waifu2x server: {} \n".format(response.status)
                    if response.status == 502:
                        message += "File probably too large \n"
                        message += "Please only upload files smaller than 5MB and 1500x1500px"
                    await ctx.send(message)
        except Exception as e:
            print(repr(e))


async def setup(bot):
    await bot.add_cog(Waifu2x(bot))
