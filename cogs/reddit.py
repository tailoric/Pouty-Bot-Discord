import json
import aiohttp
import re
import datetime
import discord
from discord.ext import commands, tasks
from os import path
from .utils import checks
import asyncio


class Reddit(commands.Cog):
    """
    cog for automatically removing reddit links that break rule 3
    """

    def __init__(self, bot):
        with open("data/reddit_credentials.json", "r") as cred_file:
            self.bot = bot
            self.credentials = json.load(cred_file)
            if self.credentials:
                self.client_id = self.credentials['client_id']
                self.secret = self.credentials['client_secret']
                self.auth = aiohttp.BasicAuth(self.client_id, self.secret)
                self.headers = {'User-Agent': 'Discord Bot by /u/Saikimo',
                                'Content-Type': 'application/json'}
            self.session = aiohttp.ClientSession()
            self.reddit_settings_path = "data/reddit_settings.json"
            self.checker_channel = None
            if not path.exists(self.reddit_settings_path):
                file = open(self.reddit_settings_path, 'w')
                json.dump({'channel': None}, file)
            with open(self.reddit_settings_path, 'r') as f:
                settings = json.load(f)
                self.checker_channel = self.bot.get_channel(settings['channel'])
                self.reddit_channel = self.bot.get_channel(settings.get("reddit_channel", None))
            self.last_stickied_post_time = datetime.datetime.utcnow()
            self.check_reddit_for_pinned_threads.start()
            self.bot.loop.create_task(self.create_last_posts_table())

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())
        self.check_reddit_for_pinned_threads.stop()

    async def create_last_posts_table(self):
        async with self.bot.db.acquire() as connection:
            query = "CREATE TABLE IF NOT EXISTS stickied_threads(" \
                    "post_id varchar(255) primary key," \
                    "created timestamp)"
            async with connection.transaction():
                await connection.execute(query)

    async def fetch_last_stickied_entries(self):
        query = "SELECT post_id, created from stickied_threads"
        async with self.bot.db.acquire() as connection:
            return await connection.fetch(query)
    async def insert_post(self, id, created):
        query = ("INSERT INTO stickied_threads VALUES ($1, $2);"
                 )
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare(query)
            async with connection.transaction():
                await statement.fetch(id, created)


    @commands.command(name="redditc")
    @checks.is_owner_or_moderator()
    async def setup_reddit_channel(self, ctx):
        """set up the channel for posting stickied threads"""
        with open(self.reddit_settings_path, 'r+') as f:
            settings = json.load(f)
            settings["reddit_channel"] = ctx.channel.id
            f.seek(0)
            json.dump(settings, f)
        self.reddit_channel = ctx.channel
        await ctx.send(f"{ctx.channel.mention} set up as the reddit channel for announcements")

    async def edit_embed_with_info(self, permalink, message):
        post_obj = {"permalink": permalink}
        comment = await self.get_stickied_comment(post_obj)
        while not comment:
            await asyncio.sleep(30)
            comment = await self.get_stickied_comment(post_obj)
        embed = message.embeds[0]
        embed.description = comment["data"]["body"][:500]+"..."
        await message.edit(embed=embed)

    @tasks.loop(minutes=1)
    async def check_reddit_for_pinned_threads(self):
        async with self.session.get(url="https://reddit.com/r/Animemes.json", auth=self.auth,
                                    headers=self.headers) as resp:
            if resp.status == 200:
                resp_data = await resp.json()
                stickied_post = [post['data'] for post in resp_data["data"]["children"] if post['data']["stickied"]]
                last_posts = await self.fetch_last_stickied_entries()
                if not last_posts:
                    for post in stickied_post:
                        post_creation = datetime.datetime.utcnow()
                        await self.insert_post(post["id"], post_creation)
                for post in stickied_post:
                    post_creation = datetime.datetime.utcnow()
                    if post["id"] not in [p["post_id"] for p in last_posts]:
                        embed = await self.build_embed_for_stickied_thread(post)
                        if embed:
                            sent_message = await self.reddit_channel.send(embed=embed)
                            await self.insert_post(post["id"], post_creation)
                            if embed.description == '\u200b':
                                await self.edit_embed_with_info(post["permalink"], sent_message)

    async def get_stickied_comment(self, post):
        async with self.session.get(url=f"https://reddit.com{post['permalink']}.json") as resp:
            if resp.status == 200:
                json_data = await resp.json()
                try:
                    return next(comment for comment in json_data[1]["data"]["children"] if comment["data"]["stickied"])
                except StopIteration:
                    return None
            else:
                return None

    async def build_embed_for_stickied_thread(self, post):
        async with self.session.get(url="https://reddit.com/r/Animemes/about.json", auth=self.auth,
                                    headers=self.headers) as resp:
            if resp.status == 200:
                resp_data = await resp.json()
                sub_data = resp_data["data"]
                if post["is_self"]:
                    embed = discord.Embed(title=post["title"], timestamp=datetime.datetime.utcfromtimestamp(post["created_utc"]),
                                          url=post["url"], description=post["selftext"][:500]+"...",
                                          color=discord.Colour(int(sub_data["primary_color"].strip("#"), 16)))
                    embed.set_thumbnail(url=sub_data["header_img"])
                else:
                    stickied_comment = await self.get_stickied_comment(post)
                    embed = discord.Embed(title=post["title"],
                                          timestamp=datetime.datetime.utcfromtimestamp(post["created_utc"]),
                                          url=f"https://reddit.com{post['permalink']}",
                                          color=discord.Colour(int(sub_data["primary_color"].strip("#"), 16)),
                                          description=stickied_comment["data"]["body"][:500]+"..." if stickied_comment
                                          else "\u200b")
                    if post["over_18"]:
                        embed.set_thumbnail(url=sub_data["header_img"])
                    elif "image" in post["post_hint"]:
                        embed.set_image(url=post["url"])
                    elif post["thumbnail"] != "default" and post["thumbnail"] != "spoiler":
                        embed.set_thumbnail(url=post["thumbnail"])
                    else:
                        embed.set_thumbnail(url=sub_data["header_img"])

                embed.set_author(name=post["author"], url=f"https://reddit.com/user/{post['author']}")
                embed.set_footer(icon_url=sub_data["icon_img"], text="Animemes")
                return embed


    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if "subreddit-discussion" in after.channel.name.lower() or 522729174780084225 == after.channel.id:
            return
        contains_reddit_link_regex = re.compile("https://(\w+\.)?redd\.?it(.com/(r/\w+/)?comments)?/(\w+)",
                                                re.MULTILINE)
        match = contains_reddit_link_regex.search(after.content)
        if not match:
            return
        if match.group(1) and match.group(1).startswith('v'):
            vid_url = match.string[match.span()[0]: match.span()[1]]
            async with self.session.get(url=vid_url, auth=self.auth, headers=self.headers) as response:
                if response.status == 200:
                    url = str(response.url) + '.json'
        else:
            url = "https://reddit.com/comments/" + match.group(4) + ".json"
        async with self.session.get(url=url, auth=self.auth, headers=self.headers) as response:
            if response.status == 200:
                json_dump = await response.json()
                post_data = json_dump[0]['data']['children'][0]['data']
                creation_time = datetime.datetime.utcfromtimestamp(int(post_data['created_utc']))
                now = datetime.datetime.utcnow()
                difference = now - creation_time
                subreddit = post_data['subreddit']
                is_stickied = post_data['stickied']
                removed_by_category = post_data['removed_by_category']

                if not subreddit == "Animemes":
                    return
                if removed_by_category:
                    return
                if difference.total_seconds() < 12 * 3600 and not is_stickied:
                    await after.delete()
                    await after.channel.send(after.author.mention + " reddit thread automatically removed because " +
                                             "it is too recent **(Discord server rule 3)**")
                    if self.checker_channel:
                        await self.checker_channel.send(
                            "Warned {0}\nposted a reddit link that was too recent".format(after.author.mention))

    @commands.Cog.listener()
    async def on_message(self, message):
        if "subreddit-discussion" in message.channel.name.lower() or 522729174780084225 == message.channel.id:
            return
        contains_reddit_link_regex = re.compile("https://(\w+\.)?redd\.?it(.com/(r/\w+/)?comments)?/(\w+)",
                                                re.MULTILINE)
        match = contains_reddit_link_regex.search(message.content)
        url = message.content
        if not match:
            return
        if match.group(1) and match.group(1).startswith('v'):
            vid_url = match.string[match.span()[0]: match.span()[1]]
            async with self.session.get(url=vid_url, auth=self.auth, headers=self.headers) as response:
                if response.status == 200:
                    url = str(response.url) + '.json'
        else:
            url = "https://reddit.com/comments/" + match.group(4) + ".json"
        async with self.session.get(url=url, auth=self.auth, headers=self.headers) as response:
            if response.status == 200:
                json_dump = await response.json()
                post_data = json_dump[0]['data']['children'][0]['data']
                creation_time = datetime.datetime.utcfromtimestamp(int(post_data['created_utc']))
                now = datetime.datetime.utcnow()
                difference = now - creation_time
                subreddit = post_data['subreddit']
                is_stickied = post_data['stickied']
                removed_by_category = post_data['removed_by_category']
                if not subreddit == "Animemes":
                    return
                if removed_by_category:
                    return
                if difference.total_seconds() < 12 * 3600 and not is_stickied:
                    await message.delete()
                    await message.channel.send(
                        message.author.mention + " reddit thread automatically removed because " +
                        "it is too recent **(Discord server rule 3)**")
                    if self.checker_channel:
                        await self.checker_channel.send(
                            "Warned {0}\nposted a reddit link that was too recent".format(message.author.mention))

    @checks.is_owner_or_moderator()
    @commands.command(pass_context=True, hidden=True)
    async def setup_checker_channel(self, ctx):
        channel = ctx.message.channel
        if not path.exists(self.reddit_settings_path):
            open(self.reddit_settings_path, 'w').close()
        with open(self.reddit_settings_path, 'w') as f:
            self.checker_channel = channel
            settings = {'channel': channel.id}
            json.dump(settings, f)


def setup(bot):
    bot.add_cog(Reddit(bot))
