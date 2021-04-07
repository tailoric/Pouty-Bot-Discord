from discord.ext import commands
import discord
import aiohttp
import re
import io
from pathlib import Path
import json
import logging

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
        self.pixiv_url_regex = re.compile(r".*pixiv.net.*/artworks/(\d+)")
        self.twitter_url_regex = re.compile(r"https://twitter.com/(?P<user>\w+)/status/(?P<post_id>\d+)")
        path = Path('config/twitter.json')
        self.logger = logging.getLogger('PoutyBot')
        if path.exists():
            with path.open('r') as f:
                self.twitter_settings = json.load(f)
                self.twitter_header = {
                        "Authorization" : f"Bearer {self.twitter_settings.get('token')}"
                        }
        else:
            self.logger.warn("No twitter configs found")
            self.twitter_settings = None
            self.twitter_header = None           

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    @commands.command(name="pixiv")
    async def pixiv_expand(self, ctx, link):
        """
        expand a pixiv link into the first 10 images of a pixiv gallery/artwork link
        """
        details_url = "https://www.pixiv.net/touch/ajax/illust/details?illust_id={}"
        match_url= self.pixiv_url_regex.match(link)
        if not match_url:
            return await ctx.send("Could not extract an id from this link.")
        illust_id = match_url.group(1)
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

    @commands.command(name="twitter")
    async def twitter_expand(self, ctx, link):
        """
        expand a twitter link to its images
        """
        if not self.twitter_header:
            return await ctx.send("Command disabled since host has no authentication token")
        match = self.twitter_url_regex.match(link)
        if not match:
            return await ctx.send("Couldn't get id from link")
        await ctx.trigger_typing()
        api_url = f"https://api.twitter.com/2/tweets/{match.group('post_id')}?expansions=attachments.media_keys,author_id&media.fields=type,url&user.fields=profile_image_url,username"
        file_list = []
        async with self.session.get(url=api_url, headers=self.twitter_header) as response:
            if response.status < 400:
                tweet = await response.json()            
                text = tweet['data'].get('text', "No Text")
                includes = tweet.get('includes', [])
                if includes:
                    users = includes.get("users", [])
                    media = includes.get('media', [])
                else:
                    users = []
                    media = []
                for m in media:
                    if m.get('type') != 'photo':
                        continue
                    async with self.session.get(url=m.get('url')) as img:
                        filename = m.get('url').split('/')[-1]
                        if img.status < 400:
                            content_length = img.headers.get('Content-Length')
                            if content_length and int(content_length) > ctx.guild.filesize_limit:
                                continue
                            buffer = io.BytesIO(await img.read())
                            buffer.seek(0)
                            file_list.append(discord.File(fp=buffer, filename=filename))
                embed = discord.Embed(title=f"Extracted {len(file_list)} images", description=text, url=link, color=discord.Colour(0x5dbaec))
                if users:
                    user = users[0]
                    embed.set_author(name=user.get('name'), url=f"https://twitter.com/{user.get('username')}/", icon_url=user.get('profile_image_url'))
                if len(file_list) == 0:
                    return await ctx.send("Sorry no images found in that Tweet")
                await ctx.send(embed=embed, files=file_list)
                if ctx.guild.me.guild_permissions.manage_messages:
                    await ctx.message.edit(suppress=True)
            else:
                self.logger.error(await response.text())
                return await ctx.send(f"Twitter responded with status code {response.status}")



def setup(bot):
    bot.add_cog(LinkExpander(bot))
