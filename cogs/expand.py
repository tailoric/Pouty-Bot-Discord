from discord.ext import commands
import discord
import aiohttp
import re
import io

class LinkExpander(commands.Cog):
    """
    A cog for expanding links with multiple images
    """
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.pixiv_headers = {
                "Referer" : "https://pixiv.net"
                }
        self.pixiv_url_regex = re.compile(r"https://www.pixiv.net/en/artworks/(\d+)")


    @commands.command(name="pixiv")
    async def pixiv_expand(self, ctx, link):
        details_url = "https://www.pixiv.net/touch/ajax/illust/details?illust_id={}"
        illust_id = self.pixiv_url_regex.match(link).group(1)
        await ctx.trigger_typing()
        async with self.session.get(details_url.format(illust_id)) as resp:
            if resp.status < 400:
                details = await resp.json()
                details = details['body']['illust_details']

            else:
                return await ctx.send(f"Pixiv replied with error code: {resp.status}")
            pages = details.get('manga_a', [{'url_big': details.get('url_big')}])
            file_list = []
            stopped = False
            for page in pages:
                img_url = page.get('url_big')
                if not img_url:
                    continue
                async with self.session.get(img_url, headers=self.pixiv_headers) as img:
                    if img.status < 400:
                        content_length = img.headers.get('Content-Length')
                        if content_length and int(content_length) > ctx.guild.filesize_limit:
                            continue
                        filename= img_url.split(r"/")[-1]
                        img_buffer = io.BytesIO(await img.read())
                        img_buffer.seek(0)
                        file_list.append(discord.File(img_buffer, filename=filename))
                        if len(file_list) == 10:
                            stopped = True
                            break
            if len(file_list) == 0:
                return await ctx.send("Could not expand link, something went wrong")
            message = "the first 10 images of this gallery" if stopped else None
            await ctx.send(content=message, files=file_list[0:10])
            if ctx.guild.me.guild_permissions.manage_messages:
                await ctx.message.edit(suppress=True)



def setup(bot):
    bot.add_cog(LinkExpander(bot))
