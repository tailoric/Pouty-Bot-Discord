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
from discord import app_commands
from functools import partial 
from itertools import filterfalse
from pathlib import Path
from textwrap import shorten
from yt_dlp import YoutubeDL, DownloadError
from typing import Optional

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
        self.twitter_url_regex = re.compile(r"https://(?:\w*\.)?([vf]x)?tw(i|x)tter\.com/(?P<user>\w+)/status/(?P<post_id>\d+)")
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

    async def cog_unload(self):
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
            await ctx.typing()
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
            await ctx.typing()
        except:
            self.logger.exception("error during typing")
        params = {
                "expansions": "attachments.media_keys,author_id,referenced_tweets.id",
                "media.fields" : "type,url",
                "user.fields" : "profile_image_url,username",
                "tweet.fields": "attachments"
                }
        api_url = "https://api.twitter.com/2/tweets/{}"
        file_list = []
        async with self.session.get(url=api_url.format(match.group('post_id')), headers=self.twitter_header, params=params) as response:
            if response.status < 400:
                tweet = await response.json()            
                referenced = tweet['data'].get("referenced_tweets")
                text = tweet['data'].get('text', "No Text")
                includes = tweet.get('includes', [])
                if includes:
                    users = includes.get("users", [])
                    media = includes.get('media', [])
                else:
                    users = []
                    media = []
                embed = discord.Embed(description=text.center(len(text) +4, '|') if is_spoiler else text, url=link, color=discord.Colour(0x5dbaec))
                if users:
                    user = users[0]
                    embed.set_author(name=user.get('name'), url=f"https://twitter.com/{user.get('username')}/", icon_url=user.get('profile_image_url'))
                quote_tweet = None
                if referenced and any(r['type'] == 'quoted' for r in referenced) and not media:
                    quote_tweet = next(filter(lambda r: r['type'] == 'quoted', referenced), None)
                    async with self.session.get(api_url.format(quote_tweet['id']), headers=self.twitter_header,params=params) as q_response:
                        tweet = await q_response.json()
                    includes = tweet.get('includes', [])
                    if includes:
                        users = includes.get("users", [])
                        media = includes.get('media', [])
                    else:
                        users = []
                        media = []
                videos_extracted = False
                for m in media:
                    if m.get('type') == 'video':
                        if videos_extracted:
                            continue
                        with YoutubeDL({'format': 'best'}) as ydl:
                            extract = partial(ydl.extract_info, link, download=False)
                            result = await self.bot.loop.run_in_executor(None, extract)
                            if result.get("playlist_count"):
                                entries = result.get("entries")
                            else:
                                entries = [result]
                            for entry in entries:
                                best_format = next(iter(sorted(entry.get('formats'),key=lambda v: v.get('width') * v.get('height'), reverse=True)), None)
                                filename = f"{entry.get('id')}.{best_format.get('ext')}"
                                if not best_format:
                                    continue
                                proc = await asyncio.create_subprocess_exec(f"ffmpeg", "-hide_banner", "-loglevel" , "error", "-i",  best_format.get('url'), '-c', 'copy', '-y', f'export/{filename}')
                                result, err = await proc.communicate()
                                file_size = os.path.getsize(filename=f'export/{filename}')
                                file_limit = 8388608
                                if ctx.guild:
                                    file_limit = ctx.guild.filesize_limit
                                if file_size > file_limit:
                                    os.remove(f"export/{filename}")
                                    return await ctx.send(f"The video was too big for reupload ({round(file_size/(1024 * 1024), 2)} MB)")
                                file_list.append(discord.File(f'export/{filename}', filename=filename, spoiler=is_spoiler))
                        videos_extracted = True
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
                        async with self.session.get(url=f"{m.get('url')}?name=orig") as img:
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
                if len(file_list) == 0:
                    return await ctx.send("Sorry no images found in that Tweet")
                embed.title =f"Extracted {len(file_list)} images/videos"
                if quote_tweet:
                    user = users[0]
                    embed.add_field(name="Quoted Tweet", value=f"https://twitter.com/{user.get('username')}/status/{tweet.get('data').get('id')}")
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
            url = url.partition("?")[0]
            reddit_request = f"{url}.json"

        try:
            await ctx.typing()
        except:
            self.logger.exception("error during typing")
        results = []

        post_data = {}
        headers = {'User-Agent': 'https://github.com/tailoric/Pouty-Bot-Discord Pouty-Bot by /u/Saikimo'}
        resp = await self.httpx.get(url=reddit_request, headers=headers, follow_redirects=True)
        resp.raise_for_status()
        post_data = resp.json()
        post_data = post_data[0]['data']['children'][0]['data']
        embed = None
        if post_data:
            title= shorten(post_data.get('title'), 250)
            embed = (discord.Embed(title=title.center(len(title)+4, '|') if is_spoiler else title, url=f"https://www.reddit.com{post_data.get('permalink')}")
                        .set_author(name=post_data.get('subreddit_name_prefixed'),
                            url=f"https://www.reddit.com/{post_data.get('subreddit_name_prefixed')}")
                        
            )
        video_url = post_data['url']
        with YoutubeDL({'format': 'bestvideo', 'quiet': True}) as ytdl_v, YoutubeDL({'format': 'bestaudio', 'quiet': True}) as ytdl_a:
            extract_video = partial(ytdl_v.extract_info, video_url, download=False)
            extract_audio = partial(ytdl_a.extract_info, video_url, download=False)
            results = await asyncio.gather(
                    self.bot.loop.run_in_executor(None, extract_video),
                    self.bot.loop.run_in_executor(None, extract_audio),
                    return_exceptions=True
                    )
        
        results = list(filterfalse(lambda r: isinstance(r, DownloadError), results))
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

    fclyde = app_commands.Group(name="fclyde", description="get around the clyde filter for upload")

    @fclyde.command(name="file")
    @app_commands.describe(
            attachment="a file you want to upload that gets blocked by clyde",
            is_spoiler="specify if the file or image is a spoiler, please",
            warning="The content warning for a spoiler"
            )
    @app_commands.rename(
            is_spoiler="spoiler"
            )
    async def fuck_clyde_file(self, interaction: discord.Interaction, attachment: discord.Attachment, warning: Optional[str], is_spoiler: bool=False) -> None:
        if is_spoiler and not warning:
            return await interaction.response.send_message("Please set a `warning:` when sending a spoiler", ephemeral=True)
        await interaction.response.defer()
        try:
                await interaction.followup.send(file=await attachment.to_file(spoiler=is_spoiler), content=warning if is_spoiler else None)
        except discord.HTTPException as e:
            await interaction.followup.send(content=str(e))

    @fclyde.command(name="link")
    @app_commands.describe(
            link="a link you want to send that doesn't get embedded",
            is_spoiler="specify if the file or image is a spoiler, please",
            warning="The content warning for a spoiler"
            )
    @app_commands.rename(
            is_spoiler="spoiler"
            )
    async def fuck_clyde_link(self, interaction: discord.Interaction, link:str , warning: Optional[str], is_spoiler: bool=False) -> None:
        if is_spoiler and not warning:
            return await interaction.response.send_message("Please set a `warning:` when sending a spoiler", ephemeral=True)
        try:
            await interaction.response.send_message(content=f"{warning} || {link} ||" if is_spoiler else link)
        except discord.HTTPException as e:
            await interaction.followup.send(content=str(e))

async def setup(bot):
    await bot.add_cog(LinkExpander(bot))
