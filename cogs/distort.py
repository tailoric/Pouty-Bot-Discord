from discord import File
from discord.ext import commands
from typing import Optional
import aiohttp
import asyncio
import io
import sys


class Distort(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.allowed_file_extensions = ['.png', '.jpg', '.jpeg', '.gif']

    @commands.command()
    async def distort(self, ctx: commands.Context, link: Optional[str]):
        if 'win32' in sys.platform:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        message = ctx.message
        if message.attachments:
            filetype = message.attachments[0].url[-4:]
            if filetype not in self.allowed_file_extensions:
                await ctx.send("not allowed filetype only images or gifs allowed")
            await message.attachments[0].save("data\\temp"+filetype)
        else:
            async with self.session.get(url=link) as r:
                filetype = link[-4:]
                if filetype not in self.allowed_file_extensions:
                    await ctx.send("not allowed filetype only images or gifs allowed")
                if r.status == 200:
                    with open("data/temp"+filetype, "wb") as f:
                        buffer = io.BytesIO(await r.read())
                        f.write(buffer.read())
        proc = await asyncio.create_subprocess_exec(
            "convert",'data\\temp'+filetype, '-liquid-rescale', '50%x50%', 'data\\temp_distort'+filetype
        )
        await proc.communicate()
        await ctx.send(file=File('data\\temp_distort'+filetype))




def setup(bot: commands.Bot):
    bot.add_cog(Distort(bot))
