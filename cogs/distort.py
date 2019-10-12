from discord import File, PartialEmoji, Member
from discord.ext import commands
from typing import Optional, Union
import aiohttp
import asyncio
import io
import uuid
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
    async def distort(self, ctx: commands.Context, link: Optional[Union[PartialEmoji,Member,str]]):
        """
        creates a distorted version of an image, works with direct upload and
        image link
        IMPORTANT: image link needs to end in a filename (gif,png,jpg)
        """
        message = ctx.message
        if message.attachments:
            url = str(message.attachments[0].url)
            filetype = url[url.rfind('.'):]
            pos = url.rfind("/")
            filename = url[pos+1:]
            if filetype.lower() not in self.allowed_file_extensions:
                await ctx.send("not allowed filetype only images or gifs allowed")
                return
            await message.attachments[0].save(f"data/{filename}")
        else:
            if isinstance(link, PartialEmoji):
                filetype = str(link.url)[str(link.url).rfind("."):]
                filename = f"{link.name}{filetype}"
                await link.url.save(f"data/{filename}")
            elif isinstance(link, Member):
                ctx.author = link
                await ctx.invoke(self._me)
                return
            else:
                try:
                    async with self.session.get(url=link) as r:
                        filetype = link[link.rfind('.'):]
                        pos = link.rfind("/")
                        filename = link[pos+1:]
                        if filetype.lower() not in self.allowed_file_extensions:
                            await ctx.send("not allowed filetype only images or gifs allowed")
                            return
                        if r.status == 200:
                            with open(f"data/{filename}", "wb") as f:
                                buffer = io.BytesIO(await r.read())
                                f.write(buffer.read())
                except aiohttp.InvalidURL:
                    await ctx.send("this command only works with custom emojis, direct image links or usernames or mentions.")
                    return
        async with ctx.typing():
            output_file = await self.spawn_magick(filename, filetype)
            await ctx.send(file=File(output_file))
            os.remove(output_file)

    @distort.command(name="me")
    async def _me(self, ctx):
        """
        distort your user profile pic
        """
        asset = ctx.author.avatar_url_as(static_format="png")
        filetype = str(asset)[str(asset).rfind("."):str(asset).rfind("?")]
        async with ctx.typing():
            filename = f"{ctx.author.id}{filetype}"
            await asset.save(f"data/{filename}")
            output_path = await self.spawn_magick(filename=filename, filetype=filetype)
            await ctx.send(file=File(output_path))

    async def spawn_magick(self, filename, filetype):
        output_path_temp = os.path.join('data', filename)
        output_path_distort = os.path.join('data', str(uuid.uuid4()) + filetype)
        proc = await asyncio.create_subprocess_exec(
            self.image_magick_command, output_path_temp, '-layers', 'coalesce', '-liquid-rescale', '50%x50%',
            '-resize', '200%', output_path_distort
        )
        await proc.communicate()
        os.remove(output_path_temp)
        return output_path_distort


def setup(bot: commands.Bot):
    bot.add_cog(Distort(bot))
