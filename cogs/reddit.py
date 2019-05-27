import json
import aiohttp
import re
import datetime
from discord.ext import commands
from os import path
from .utils import checks


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

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())


    @commands.Cog.listener()
    async def on_message(self, message):
        contains_reddit_link_regex = re.compile("https://(\w+\.)?redd\.?it(.com/(r/\w+/)?comments)?/(\w+)", re.MULTILINE)
        match = contains_reddit_link_regex.search(message.content)
        url = message.content
        if not match:
            return
        if match.group(1) and match.group(1).startswith('v'):
            vid_url = match.string[match.span()[0]: match.span()[1]]
            async with self.session.get(url=vid_url, auth=self.auth, headers=self.headers) as response:
                if response.status == 200:
                    url = response.url + '.json'
        else:
            url = "https://reddit.com/comments/"+match.group(4)+".json"
        print(url)
        async with self.session.get(url=url, auth=self.auth, headers=self.headers) as response:
            if response.status == 200:
                json_dump = await response.json()
                post_data = json_dump[0]['data']['children'][0]['data']
                creation_time = datetime.datetime.utcfromtimestamp(int(post_data['created_utc']))
                now = datetime.datetime.utcnow()
                difference = now - creation_time
                subreddit = post_data['subreddit']
                is_stickied = post_data['stickied']
                if not subreddit == "Animemes":
                    return
                if difference.total_seconds() < 12 * 3600 and not is_stickied:
                    await message.delete()
                    await message.channel.send(message.author.mention + " reddit thread automatically removed because "+
                                                                 "it is too recent **(Discord server rule 3)**")
                    if self.checker_channel:
                        await self.checker_channel.send("Warned {0}\nposted a reddit link that was too recent".format(message.author.mention))


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
