from discord import File
from discord.ext import commands
from typing import Optional
import aiohttp
import asyncio
import io
import os
import sys


class Distort(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.allowed_file_extensions = ['.png', '.jpg', '.jpeg', '.gif']
        if 'win32' in sys.platform:
            self.image_magick_command = "magick"
        else:
            self.image_magick_command = "convert"

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    @commands.group(invoke_without_command=True)
    async def distort(self, ctx: commands.Context, link: Optional[str]):
        """
        creates a distorted version of an image, works with direct upload and
        image link
        IMPORTANT: image link needs to end in a filename (gif,png,jpg)
        """
        message = ctx.message
        if message.attachments:
            url = message.attachments[0].url
            filetype = url[url.rfind('.'):]
            if filetype.lower() not in self.allowed_file_extensions:
                await ctx.send("not allowed filetype only images or gifs allowed")
                return
            await message.attachments[0].save("data/temp" + filetype)
        else:
            async with self.session.get(url=link) as r:
                filetype = link[link.rfind('.'):]
                if filetype.lower() not in self.allowed_file_extensions:
                    await ctx.send("not allowed filetype only images or gifs allowed")
                    return
                if r.status == 200:
                    with open("data/temp" + filetype, "wb") as f:
                        buffer = io.BytesIO(await r.read())
                        f.write(buffer.read())
        async with ctx.typing():
            await self.spawn_magick(filetype)
            await ctx.send(file=File('data/temp_distort' + filetype))

    @distort.command(name="me")
    async def _me(self, ctx):
        """
        distort your user profile pic
        """
        asset = ctx.author.avatar_url_as(static_format="png")
        filetype = str(asset)[str(asset).rfind("."):str(asset).rfind("?")]
        async with ctx.typing():
            await asset.save("data/temp" + filetype)
            await self.spawn_magick(filetype)
            await ctx.send(file=File("data/temp_distort" + filetype))

    async def spawn_magick(self, filetype):
        output_path_temp = os.path.join('data', 'temp' + filetype)
        output_path_distort = os.path.join('data', 'temp_distort' + filetype)
        proc = await asyncio.create_subprocess_exec(
            self.image_magick_command, output_path_temp, '-layers', 'coalesce', '-liquid-rescale', '50%x50%',
            '-resize', '200%', output_path_distort
        )
        await proc.communicate()


def setup(bot: commands.Bot):
    bot.add_cog(Distort(bot))
