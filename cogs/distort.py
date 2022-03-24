from discord import File, PartialEmoji, Member
from discord.ext import commands
from typing import Optional, Union
import aiohttp
import asyncio
import io
import uuid
import os
import sys
import uuid

class Distort(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.allowed_file_extensions = ['png', 'jpg', 'jpeg', 'gif']
        if 'win32' in sys.platform:
            self.image_magick_command = "magick"
        else:
            self.image_magick_command = "convert"

    async def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

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

    @commands.command()
    async def blur(self, ctx: commands.Context, intensity: Optional[int], link: Optional[Union[PartialEmoji, Member, str]]):
        """
        blur command applies radial blur to image
        allowed intensity settings are between 1 and 15
        """
        if intensity is None:
            intensity = 5
        elif intensity < 1:
            intensity = 1
        elif intensity > 15:
            intensity = 15
        if ctx.message.attachments:
            url = str(ctx.message.attachments[0].url)
            filetype = url[url.rfind('.') + 1:]
            pos = url.rfind("/")
            filename = url[pos + 1:]
            if filetype.lower() not in self.allowed_file_extensions:
                await ctx.send("not allowed filetype only images or gifs allowed")
                return
            await ctx.message.attachments[0].save(f"data/{filename}")
        elif isinstance(link, PartialEmoji):
            filetype = str(link.url)[str(link.url).rfind("."):]
            filename = f"{link.name}{filetype}"
            await link.url.save(f"data/{filename}")
        elif isinstance(link, Member):
            asset = link.avatar.replace(size=512, format="png")
            filetype = ".png"
            filename = str(ctx.author.id) + filetype
            await asset.save(f"data/{ctx.author.id}{filetype}")
        elif link is None or link.lower() == "me":
            asset = ctx.author.avatar.replace(size=512, format="png")
            filetype = ".png"
            filename = str(ctx.author.id) + filetype
            await asset.save(f"data/{ctx.author.id}{filetype}")
        else:
            try:
                async with self.session.get(url=link) as r:
                    filetype = r.headers["Content-Type"].split("/")[1]
                    filename = f"{uuid.uuid4()}.{filetype}"
                    if filetype.lower() not in self.allowed_file_extensions:
                        await ctx.send("not allowed filetype only images or gifs allowed")
                        return
                    if r.status == 200:
                        with open(f"data/{filename}", "wb") as f:
                            buffer = io.BytesIO(await r.read())
                            f.write(buffer.read())
            except aiohttp.InvalidURL:
                await ctx.send(
                    "this command only works with custom emojis, direct image links or usernames or mentions.")
                return
        async with ctx.typing():
            output_path = await self.create_rad_blur(filename, filetype, intensity)
            await self.send_if_possible_and_delete(ctx, output_path)

    async def create_rad_blur(self, filename, filetype, intensity):
        if not filetype.startswith("."):
            filetype = "." + filetype
        output_path_temp = os.path.join('data', filename)
        output_path_blur = os.path.join('data', str(uuid.uuid4()) + filetype)
        proc = await asyncio.create_subprocess_exec(
            self.image_magick_command, output_path_temp, '-rotational-blur', str(intensity), output_path_blur
        )
        await proc.communicate()
        os.remove(output_path_temp)
        return output_path_blur

    async def send_if_possible_and_delete(self, ctx, file_path):
        size = 8388608
        if ctx.guild:
            size = ctx.guild.filesize_limit
        if os.path.getsize(file_path) < size:
            await ctx.send(file=File(file_path))
        else:
            await ctx.send("Send failed. The generated file exceeds this discord servers filesize limit.")
        os.remove(file_path)


async def setup(bot: commands.Bot):
    await bot.add_cog(Distort(bot))
