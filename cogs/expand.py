import httpx
import aiohttp
import asyncio
import discord
import io
import json
import logging
import os
import re
from discord.ext import commands
from functools import partial 
from itertools import filterfalse
from pathlib import Path
from textwrap import shorten
from youtube_dl import YoutubeDL, DownloadError

spoiler_regex = re.compile(r"\|\|\s?(?P<link>.+?)\s?\|\|")
class SpoilerLinkConverter(commands.Converter):
    async def convert(self, ctx, argument):
        if (match := spoiler_regex.search(argument)):
            link = match.group('link')
            return link.strip("<>"), True
        else:
            argument = re.split(r"\s", argument)[0]
            return argument.strip("<>"), False
        

class LinkExpander(commands.Cog):
    """
    A cog for expanding links with multiple images
    """
    def __init__(self, bot):
        if not os.path.exists('export'):
            os.mkdir('export')
        self.bot = bot
        self.httpx = httpx.AsyncClient()
        self.session = aiohttp.ClientSession()
        self.pixiv_headers = {
                "Referer" : "https://pixiv.net"
                }
        self.pixiv_url_regex = re.compile(r".*pixiv.net.*/artworks/(\d+)")
        self.twitter_url_regex = re.compile(r"https://(?:\w*\.)?twitter\.com/(?P<user>\w+)/status/(?P<post_id>\d+)")
        self.reddit_url_regex = re.compile(r"https?://(?:www)?(?:(?:v|old|new)?\.)?(?:redd\.?it)?(?:.com)?/(?:(?P<video_id>(?!r/)\w{10,15})|r|(?P<short_id>\w{4,8}))(?:/(?P<subreddit>\w+)/comments/(?P<post_id>\w+))?")
        path = Path('config/twitter.json')
        path_streamable = Path('config/streamable.json')
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
        if path_streamable.exists():
            with path_streamable.open('r') as f:
                self.streamable_auth = json.load(f)

    def cog_unload(self):
        self.bot.loop.create_task(self.httpx.aclose())
        self.bot.loop.create_task(self.session.close())

    @commands.command(name="pixiv", aliases=["pix", "pxv"])
    async def pixiv_expand(self, ctx, *, link : SpoilerLinkConverter):
        """
        expand a pixiv link into the first 10 images of a pixiv gallery/artwork link
        """
        link, is_spoiler = link
        details_url = "https://www.pixiv.net/touch/ajax/illust/details?illust_id={}"
        match_url= self.pixiv_url_regex.match(link)
        if not match_url:
            return await ctx.send("Could not extract an id from this link.")
        illust_id = match_url.group(1)
        try:
            await ctx.trigger_typing()
        except:
            self.logger.exception("failure during typing")
        async with self.session.get(details_url.format(illust_id)) as resp:
            if resp.status < 400:
                details = await resp.json()
                details = details['body']['illust_details']

            else:
                return await ctx.send(f"Pixiv replied with error code: {resp.status}")
            pages = details.get('manga_a', [{'url_big': details.get('url_big')}])
            file_list = []
            stopped = False
            total_content_length = 0
            for page in pages:
                img_url = page.get('url_big')
                if not img_url:
                    continue
                async with self.session.get(img_url, headers=self.pixiv_headers) as img:
                    if img.status < 400:
                        content_length = img.headers.get('Content-Length')
                        file_limit = 8388608
                        if ctx.guild:
                            file_limit = ctx.guild.filesize_limit
                        if content_length:
                            total_content_length += int(content_length)
                            if total_content_length >= file_limit:
                                continue
                        filename= img_url.split(r"/")[-1]
                        img_buffer = io.BytesIO(await img.read())
                        img_buffer.seek(0)
                        file_list.append(discord.File(img_buffer, filename=filename, spoiler=is_spoiler))
                        if len(file_list) == 10:
                            stopped = True
                            break
            if len(file_list) == 0:
                return await ctx.send("Could not expand link, something went wrong. Maybe the file was too large")
            message = "the first 10 images of this gallery" if stopped else None
            await ctx.send(content=message, files=file_list[0:10])
            if ctx.guild and ctx.guild.me.guild_permissions.manage_messages:
                await ctx.message.edit(suppress=True)

    @commands.command(name="twitter", aliases=['twt', 'twttr'])
    async def twitter_expand(self, ctx, * ,link: SpoilerLinkConverter):
        """
        expand a twitter link to its images
        """
        link, is_spoiler = link
        if not self.twitter_header:
            return await ctx.send("Command disabled since host has no authentication token")
        match = self.twitter_url_regex.match(link)
        if not match:
            return await ctx.send("Couldn't get id from link")
        try:
            await ctx.trigger_typing()
        except:
            self.logger.exception("error during typing")
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
                            if not best_format:
                                continue
                            proc = await asyncio.create_subprocess_exec(f"ffmpeg", "-i",  best_format.get('url'), '-c', 'copy', '-y', f'export/{filename}')
                            result, err = await proc.communicate()
                            file_size = os.path.getsize(filename=f'export/{filename}')
                            file_limit = 8388608
                            if ctx.guild:
                                file_limit = ctx.guild.filesize_limit
                            if file_size > file_limit:
                                os.remove(f"export/{filename}")
                                return await ctx.send(f"The video was too big for reupload ({round(file_size/(1024 * 1024), 2)} MB)")
                            file_list.append(discord.File(f'export/{filename}', filename=filename, spoiler=is_spoiler))
                    elif m.get('type') == 'animated_gif':
                        with YoutubeDL({'format': 'best'}) as ydl:
                            extract = partial(ydl.extract_info, link, download=False)
                            result = await self.bot.loop.run_in_executor(None, extract)
                            gif_url = result.get('formats')[0].get('url')
                            async with self.session.get(gif_url) as gif:
                                filename = gif_url.split('/')[-1]
                                content_length = gif.headers.get('Content-Length')
                                file_limit = 8388608
                                if ctx.guild:
                                    file_limit = ctx.guild.filesize_limit
                                if content_length and int(content_length) > file_limit:
                                    continue
                                buffer = io.BytesIO(await gif.read())
                                buffer.seek(0)
                                file_list.append(discord.File(fp=buffer, filename=filename, spoiler=is_spoiler))
                                
                    else:
                        async with self.session.get(url=m.get('url')) as img:
                            filename = m.get('url').split('/')[-1]
                            if img.status < 400:
                                content_length = img.headers.get('Content-Length')
                                file_limit = 8388608
                                if ctx.guild:
                                    file_limit = ctx.guild.filesize_limit
                                if content_length and int(content_length) > file_limit:
                                    continue
                                buffer = io.BytesIO(await img.read())
                                buffer.seek(0)
                                file_list.append(discord.File(fp=buffer, filename=filename, spoiler=is_spoiler))
                embed = discord.Embed(title=f"Extracted {len(file_list)} images", description=text.center(len(text) +4, '|') if is_spoiler else text, url=link, color=discord.Colour(0x5dbaec))
                if users:
                    user = users[0]
                    embed.set_author(name=user.get('name'), url=f"https://twitter.com/{user.get('username')}/", icon_url=user.get('profile_image_url'))
                if len(file_list) == 0:
                    return await ctx.send("Sorry no images found in that Tweet")
                await ctx.send(embed=embed, files=file_list)
                if ctx.guild and ctx.guild.me.guild_permissions.manage_messages:
                    await ctx.message.edit(suppress=True)
                for file in file_list:
                    if hasattr(file.fp, 'name'):
                        os.remove(file.fp.name)

            else:
                self.logger.error(await response.text())
                return await ctx.send(f"Twitter responded with status code {response.status}")

    @commands.command(name="vreddit")
    async def expand_reddit_video(self, ctx, *, url : SpoilerLinkConverter):
        """
        reupload a reddit hosted video 
        preferably use the v.redd.it link but it should work with threads too
        """
        url, is_spoiler = url
        reddit_match = self.reddit_url_regex.match(url)
        if not reddit_match:
            return await ctx.send("Please send a valid reddit link")
        
        if reddit_match.group('video_id'):
            reddit_request = f"https://www.reddit.com/video/{reddit_match.group('video_id')}.json"
        elif reddit_match.group('short_id'):
            url = f"https://www.reddit.com/{reddit_match.group('short_id')}"
            reddit_request = f"https://www.reddit.com/{reddit_match.group('short_id')}.json"
        else:
            reddit_request = f"https://www.reddit.com/{reddit_match.group('post_id')}.json"

        try:
            await ctx.trigger_typing()
        except:
            self.logger.exception("error during typing")
        results = []

        post_data = {}
        headers = {'User-Agent': 'https://github.com/tailoric/Pouty-Bot-Discord Pouty-Bot by /u/Saikimo'}
        resp = await self.httpx.get(url=reddit_request, headers=headers)
        post_data = resp.json()
        post_data = post_data[0]['data']['children'][0]['data']
        embed = None
        if post_data:
            title= shorten(post_data.get('title'), 250)
            embed = (discord.Embed(title=title.center(len(title)+4, '|') if is_spoiler else title, url=f"https://reddit.com{post_data.get('permalink')}")
                        .set_author(name=post_data.get('subreddit_name_prefixed'),
                            url=f"https://reddit.com/{post_data.get('subreddit_name_prefixed')}")
                        
            )
        results = list(filterfalse(lambda r: isinstance(r, DownloadError), results))
        video_url = post_data['url']
        with YoutubeDL({'format': 'bestvideo', 'quiet': False}) as ytdl_v, YoutubeDL({'format': 'bestaudio', 'quiet': False}) as ytdl_a:
            extract_video = partial(ytdl_v.extract_info, video_url, download=False)
            extract_audio = partial(ytdl_a.extract_info, video_url, download=False)
            results = await asyncio.gather(
                    self.bot.loop.run_in_executor(None, extract_video),
                    self.bot.loop.run_in_executor(None, extract_audio),
                    return_exceptions=True
                    )
        
        if len(results) == 0:
            return await ctx.send("No video found please check if this link contains a video file (not a gif) preferably use the v.redd.it link")
        filename = f"{results[0].get('id')}.{results[0].get('ext')}"
        if len(results) == 1:
            proc = await asyncio.create_subprocess_exec(f"ffmpeg", "-hide_banner", "-loglevel" , "error","-i",  results[0].get('url'), '-c', 'copy', '-y', f'export/{filename}')
        else:
            proc = await asyncio.create_subprocess_exec(f"ffmpeg", "-hide_banner", "-loglevel" , "error","-i",  results[0].get('url'), '-i', results[1].get('url'),  '-c', 'copy', '-y', f'export/{filename}')
        result, err = await proc.communicate()
        file_size = os.path.getsize(filename=f'export/{filename}')
        
        file_limit = 8388608
        if ctx.guild:
            file_limit = ctx.guild.filesize_limit
        if file_size > file_limit:
            os.remove(f"export/{filename}")
            return await ctx.send(f"The video was too big for reupload ({round(file_size/(1024 * 1024), 2)} MB)")
        await ctx.send(embed=embed, file=discord.File(f'export/{filename}', filename=filename, spoiler=is_spoiler))
        if ctx.guild and ctx.guild.me.guild_permissions.manage_messages:
            await ctx.message.edit(suppress=True)
        os.remove(f'export/{filename}')

    async def check_video_status(self, message, vid_id):
        status = 1
        count = 0
        while status == 1 and count < 6:
            async with self.session.get(f"https://api.streamable.com/videos/{vid_id}") as resp:
                if resp.status < 400:
                    data = await resp.json()
                    status = data.get('status')
            count += 1
            await asyncio.sleep(20)
        if status != 1:
            await message.edit(content=message.content + " ")


def setup(bot):
    bot.add_cog(LinkExpander(bot))
