from discord.ext import commands
import discord
import aiohttp
import asyncio
from youtube_dl import YoutubeDL, DownloadError
import re
import io
from functools import partial
from pathlib import Path
import json
import logging
import os

class LinkExpander(commands.Cog):
    """
    A cog for expanding links with multiple images
    """
    def __init__(self, bot):
        if not os.path.exists('export'):
            os.mkdir('export')
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.pixiv_headers = {
                "Referer" : "https://pixiv.net"
                }
        self.pixiv_url_regex = re.compile(r".*pixiv.net.*/artworks/(\d+)")
        self.twitter_url_regex = re.compile(r"https://twitter.com/(?P<user>\w+)/status/(?P<post_id>\d+)")
        self.reddit_url_regex = re.compile(r"https?://(?:(?:v|old|new)?\.)?(?:redd\.?it)?(?:.com)?")
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
        link = link.strip('<>')
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
        link = link.strip('<>')
        if not self.twitter_header:
            return await ctx.send("Command disabled since host has no authentication token")
        match = self.twitter_url_regex.match(link)
        if not match:
            return await ctx.send("Couldn't get id from link")
        await ctx.trigger_typing()
        params = {
                "expansions": "attachments.media_keys,author_id",
                "media.fields" : "type,url",
                "user.fields" : "profile_image_url,username",
                "tweet.fields": "attachments"
                }
        api_url = f"https://api.twitter.com/2/tweets/{match.group('post_id')}"
        file_list = []
        async with self.session.get(url=api_url, headers=self.twitter_header, params=params) as response:
            if response.status < 400:
                tweet = await response.json()            
                #print(json.dumps(tweet, indent=2))
                text = tweet['data'].get('text', "No Text")
                includes = tweet.get('includes', [])
                if includes:
                    users = includes.get("users", [])
                    media = includes.get('media', [])
                else:
                    users = []
                    media = []
                for m in media:
                    if m.get('type') == 'video':
                        with YoutubeDL({'format': 'best'}) as ydl:
                            extract = partial(ydl.extract_info, link, download=False)
                            result = await self.bot.loop.run_in_executor(None, extract)
                            best_format = next(iter(sorted(result.get('formats'),key=lambda v: v.get('width') * v.get('height'), reverse=True)), None)
                            filename = f"{match.group('post_id')}.{best_format.get('ext')}"
                            print(json.dumps(best_format, indent=2))
                            if not best_format:
                                continue
                            proc = await asyncio.create_subprocess_exec(f"ffmpeg", "-i",  best_format.get('url'), '-c', 'copy', '-y', f'export/{filename}')
                            result, err = await proc.communicate()
                            file_size = os.path.getsize(filename=f'export/{filename}')
                            if file_size > ctx.guild.filesize_limit:
                                os.remove(f'export/{filename}')
                                return await ctx.send(f"The video was too big for reupload ({round(file_size/(1024 * 1024), 2)} MB)")
                            file_list.append(discord.File(f'export/{filename}', filename=filename))
                    elif m.get('type') == 'animated_gif':
                        with YoutubeDL({'format': 'best'}) as ydl:
                            extract = partial(ydl.extract_info, link, download=False)
                            result = await self.bot.loop.run_in_executor(None, extract)
                            print(json.dumps(result, indent=2))
                            gif_url = result.get('formats')[0].get('url')
                            async with self.session.get(gif_url) as gif:
                                filename = gif_url.split('/')[-1]
                                content_length = gif.headers.get('Content-Length')
                                print(content_length)
                                if content_length and int(content_length) > ctx.guild.filesize_limit:
                                    continue
                                buffer = io.BytesIO(await gif.read())
                                buffer.seek(0)
                                file_list.append(discord.File(fp=buffer, filename=filename))
                                
                    else:
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
                for file in file_list:
                    if hasattr(file.fp, 'name'):
                        os.remove(file.fp.name)

            else:
                self.logger.error(await response.text())
                return await ctx.send(f"Twitter responded with status code {response.status}")

    @commands.command(name="vreddit")
    async def expand_reddit_video(self, ctx, url):
        """
        reupload a reddit hosted video 
        preferably use the v.redd.it link but it should work with threads too
        """
        if not self.reddit_url_regex.match(url):
            return await ctx.send("Please send a valid reddit link")

        await ctx.trigger_typing()
        with YoutubeDL({'format': 'bestvideo', 'quiet': True}) as ytdl_v, YoutubeDL({'format': 'bestaudio', 'quiet': True}) as ytdl_a:
            try:
                extract_video = partial(ytdl_v.extract_info, url, download=False)
                extract_audio = partial(ytdl_a.extract_info, url, download=False)
                results = await asyncio.gather(
                            self.bot.loop.run_in_executor(None, extract_video),
                            self.bot.loop.run_in_executor(None, extract_audio)
                            )
            except DownloadError:
                return await ctx.send("Could not download a video make sure your link contains a video preferably use v.redd.it link")
            filename = f"{results[0].get('id')}.{results[0].get('ext')}"
            proc = await asyncio.create_subprocess_exec(f"ffmpeg", "-hide_banner", "-loglevel" , "error","-i",  results[0].get('url'), '-i', results[1].get('url'),  '-c', 'copy', '-y', f'export/{filename}')
            result, err = await proc.communicate()
            file_size = os.path.getsize(filename=f'export/{filename}')
            if file_size > ctx.guild.filesize_limit:
                os.remove(f'export/{filename}')
                return await ctx.send(f"The video was too big for reupload ({round(file_size/(1024 * 1024), 2)} MB)")
            await ctx.send(file=discord.File(f'export/{filename}', filename=filename))
            if ctx.guild.me.guild_permissions.manage_messages:
                await ctx.message.edit(suppress=True)
            os.remove(f'export/{filename}')


def setup(bot):
    bot.add_cog(LinkExpander(bot))
