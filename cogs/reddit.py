import json
import aiohttp
import re
import datetime


class Reddit:
    def __init__(self, bot):
        with open("data/reddit_credentials.json", "r") as cred_file:
            self.bot = bot
            self.credentials = json.load(cred_file)
            if self.credentials:
                self.client_id = self.credentials['client_id']
                self.secret = self.credentials['client_secret']
                self.auth = aiohttp.BasicAuth(self.client_id, self.secret)
                self.headers = {'User-Agent' : 'Discord Bot by /u/Saikimo'}
            self.session = aiohttp.ClientSession()

    async def on_message(self, message):
        contains_reddit_link_regex = re.compile("https://(\w+\.)?redd\.?it(.com/(r/\w+/)?comments)?/(\w+)")
        match = contains_reddit_link_regex.match(message.content)
        if not match:
            return
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
                upvotes = post_data['ups']
                is_stickied = post_data['stickied'] == "true"
                if not subreddit == "Animemes":
                    return
                if int(upvotes) < 100 and difference.total_seconds() < 12 * 3600 and not is_stickied:
                    await self.bot.delete_message(message)
                    await self.bot.send_message(message.channel, message.author.mention + " reddit thread automatically removed because "+
                                                                 "it is too recent")




def setup(bot):
    bot.add_cog(Reddit(bot))
