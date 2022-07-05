from discord import File, PartialEmoji, Member, User
from discord.ext import commands
from typing import Optional, Union
import aiohttp
import asyncio
import io
import uuid
import os
import sys
import uuid
import re
import mimetypes

from discord.user import ClientUser

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

    async def spawn_magick(self, file: io.BytesIO) -> io.BytesIO:
        proc = await asyncio.create_subprocess_exec(
            self.image_magick_command, '-', '-layers', 'coalesce', '-liquid-rescale', '50%x50%',
            '-resize', '200%', '-', stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate(file.read())
        return io.BytesIO(stdout)

    @commands.command()
    @commands.max_concurrency(number=1, per=commands.BucketType.default)
    async def distort(self, ctx: commands.Context, file:Optional[Union[PartialEmoji, User,ClientUser, str]]):
        """
        distort an emote link or attachment

        """
        f = None
        filename = None
        file_url_regex = re.compile(r"^https?://.*\.(gif|png|jpeg|jpg)")
        filetype = None
        if file and isinstance(file, PartialEmoji):
            f = io.BytesIO(await file.read())
            filename = f"{file.name}.{file.url.split('.')[-1]}"
            filetype = filename.split(".")[-1]
        elif isinstance(file, User) or isinstance(file, ClientUser) or file == "me":
            if file == "me":
                file = ctx.author
            avatar = file.avatar or file.default_avatar 
            filename = avatar.url.split("/")[-1].split("?")[0]
            filetype = filename.split(".")[-1].split("?")[0]
            f = io.BytesIO(await avatar.read())
        elif file and isinstance(file, str) and file_url_regex.match(file):
            async with self.session.get(file) as response:
                if response.content_type in ['image/png', 'image/jpeg', 'image/gif']:
                    filename = file.split("/")[-1]
                    filetype = filename.split(".")[-1]
                    f = io.BytesIO(await response.read())
        elif ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            filetype = attachment.filename.split(".")[-1]
            if (attachment.size > 1024 * 1024 and filetype == 'gif') or (attachment.size > 1024 * 1024 * 5):
                return await ctx.send("This file is too big for this command, please only submit gifs smaller than 1MB or files smaller than 5MB")
            f = io.BytesIO(await attachment.read())
            filename = attachment.filename
        if f:
            async with ctx.typing():
                filesize = len(f.read())
                if (filesize > 1024 * 1024 and filetype == 'gif') or (filesize > 1024 * 1024 * 5):
                    return await ctx.send("This file is too big for this command, please only submit gifs smaller than 1MB or files smaller than 5MB")
                f.seek(0)
                out = await self.spawn_magick(f)
                filesize = len(out.read())
                if filesize > ctx.guild.filesize_limit:
                    return await ctx.send("File too big for upload on this server")
                out.seek(0)
                outFile = File(out, filename) 
                await ctx.send(file=outFile)
        else:
            await ctx.send("No file specified")

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
