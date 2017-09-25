from discord.ext import commands
import discord
import aiohttp
import json
import os
import datetime
from dateutil import parser
import asyncio
from asyncio import Lock
import time
import re

class Helper:
    def __init__(self, session, bot, auth_file):
        self.bot = bot
        self.session = session
        self.auth_file = auth_file

    async def lookup_tags(self, tags, **kwargs):
        params = {'tags' : tags}
        for key, value in kwargs.items():
            params[key] = value
        with open(self.auth_file) as file:
            data = json.load(file)
            user = data['user']
            api_key = data['api_key']
        auth = aiohttp.BasicAuth(user, api_key)
        url = 'http://danbooru.donmai.us'
        async with self.session.get('{}/posts.json'.format(url), params=params, auth=auth) as response:
            if response.status == 200:
                json_dump = await response.json()
                for image in json_dump:
                    image['file_url'] = url + image['file_url']
                return json_dump

class Dansub:

    def __init__(self, users, tags, server: discord.Server, channel: discord.Channel):
        self.users = list()
        if type(users) == list:
            self.users += users
        else:
            self.users.append(users)
        self.tags = list()
        self.tags += tags
        self.server = server
        self.channel = channel
        self.old_timestamp = None
        self.new_timestamp = datetime.datetime
        self.already_posted = list()
        self.feed_file = 'data/danbooru/subs/{}.json'.format(self.tags_to_filename())

    def users_to_mention(self):
        mention_string = ','.join(user.mention for user in self.users)
        return mention_string

    def tags_to_string(self):
        self.tags.sort()
        return ' '.join(self.tags)

    def compare_tags(self,tags):
        tags.sort()
        return tags == self.tags

    def tags_to_filename(self):
        # delete any character that isn't a word char - _ or . from the filename
        return re.sub('[^\w\-_\.]','_', self.tags_to_string())

    def sub_to_json(self):
        ret_val = dict()
        ret_val['users'] = {}
        for counter, user in enumerate(self.users):
            ret_val['users'][counter] = {}
            ret_val['users'][counter]['id'] = user.id
            ret_val['users'][counter]['name'] = user.name
            ret_val['users'][counter]['mention'] = user.mention
        ret_val['tags'] = self.tags
        ret_val['server'] = self.server.id
        ret_val['channel'] = self.channel.id
        ret_val['old_timestamp'] = str(self.old_timestamp)
        ret_val['new_timestamp'] = str(self.new_timestamp)
        ret_val['already_posted'] = self.already_posted
        return json.dumps(ret_val,indent=2)

    def write_sub_to_file(self):
        content = self.sub_to_json()
        with open(self.feed_file,'w') as file:
            file.write(content)



class Scheduler:
    def __init__(self, bot, session):
        self.bot = bot
        self.session = session
        self.subscriptions = list()
        self.auth_file = 'data/danbooru/danbooru.json'
        self.subs_file = 'data/danbooru/subs.db'
        self.retrieve_subs()
        self.schedule_task = self.bot.loop.create_task(self.schedule_task())
        self.helper = Helper(self.session,self.bot,self.auth_file)

    async def schedule_task(self):
        #iterate through all subscriptions and update information
        while(True):
            subs_copy = self.subscriptions.copy()
            for sub in subs_copy:
                new_posts = list()
                timestamp_posted = list()
                try:
                    tags = sub.tags_to_string()
                    images = await self.helper.lookup_tags(tags)
                    for image in images:
                        created = parser.parse(image['created_at'])
                        if not sub.old_timestamp:
                            sub.old_timestamp = created
                        if created > sub.old_timestamp:
                            new_posts.append(image['file_url'])
                            timestamp_posted.append(created)
                    if new_posts:
                        await self.send_new_posts(sub,new_posts)
                        sub.old_timestamp = max(timestamp_posted)
                    sub.write_sub_to_file()
                    await asyncio.sleep(25)

                except Exception as e:
                    owner =  discord.Object(id='361223543729422338')
                    await self.bot.send_message(owner,
                                                'Error during update Task: `{}`'.format(repr(e)))
                    await self.bot.send_message(owner,'during Sub: `{}`'.format(sub.tags_to_string()))
                    raise e
            self.write_to_file()
            await asyncio.sleep(15)

    def retrieve_subs(self):
        with open(self.subs_file) as f:
            lines = f.readlines()
        for line in lines:
            line = line.replace('\n','')
            line = line.replace('\'','')
            sub = self.create_sub_from_file(line)
            print(sub.tags_to_string())
            self.subscriptions.append(sub)


    def create_sub_from_file(self,json_path):
        with open(json_path) as sub_file:
            data = json.load(sub_file)
        server = self.bot.get_server(data['server'])
        channel = self.bot.get_channel(data['channel'])
        user_list = []
        for user in data['users']:
            # try to get the member through Discord and their ID
            member = server.get_member(data['users'][user]['id'])
            # if that fails create own user with the necessary information
            if member == None:
                id = data['users'][user]['id']
                name = data['users'][user]['name']
                member = discord.User(username=name,id=id)
            user_list.append(member)

        tags = data['tags']
        timestamp = data['old_timestamp']
        retrieved_sub =  Dansub(user_list,tags,server,channel)
        retrieved_sub.old_timestamp = parser.parse(timestamp)
        return  retrieved_sub



    async def send_new_posts(self, sub, new_posts):
        await self.bot.send_message(sub.channel, sub.users_to_mention())
        await self.bot.send_message(sub.channel, '`{}`'.format(sub.tags_to_string()))
        for post in new_posts:
            await self.bot.send_message(sub.channel, post)
        await self.bot.send_message(sub.channel, '`{}`'.format(sub.tags_to_string()))

    def find_matching_subs(self, tags, subs, image):
        matched_subs = list()
        for sub in subs:
            if sub.tags_to_string() in image['tag_string']:
                matched_subs.append(sub.users)
        return matched_subs


    def sort_tags(self, image):
        tags = image['tag_string'].split(' ')
        tags.sort()
        sorted_tags = ' '.join(tags)
        image['tag_string'] = sorted_tags

    def write_to_file(self):
        try:
            subscriptions = '\n'.join(sub.feed_file for sub in self.subscriptions)
            with open(self.subs_file, 'w') as f:
                f.write(subscriptions)
        except Exception as e:
            print(e)
            raise e



class Danbooru:
    def __init__(self, bot):
        self.bot = bot
        self.auth_file = 'data/danbooru/danbooru.json'
        self.session = aiohttp.ClientSession()
        self.scheduler = Scheduler(self.bot,self.session)
        self.helper = Helper(self.session,self.bot,self.auth_file)

    def _unload(self):
        self.scheduler.schedule_task.cancel()
        try:
            self.scheduler.write_to_file()
            for sub in self.scheduler.subscriptions:
                sub.write_sub_to_file()
                del sub
            self.session.close()
            del self.scheduler
        except Exception as e:
            print(e)
            raise e

    @commands.command()
    async def dan(self, *, tags):
        image = await self.helper.lookup_tags(tags,limit='1')
        await self.bot.say(image[0]['file_url'])

    @commands.command()
    async def danr(self, *, tags):
        image = await self.helper.lookup_tags(tags,limit='1',random='true')
        await self.bot.say(image[0]['file_url'])


    @commands.group(pass_context=True)
    async def dans(self, ctx):
        '''
        Danbooru subscribing service
        '''
        if ctx.invoked_subcommand is None:
            await self.bot.say("invalid command use `.help dans`")

    @dans.command(pass_context=True)
    async def sub(self, ctx, *, tags):
        tags_list = tags.split(' ')
        message = ctx.message
        for sub in self.scheduler.subscriptions:
            if sub.compare_tags(tags_list):
                await self.bot.reply(' You are already subscribed to those tags')
                return
        try:
            new_sub = Dansub(message.author,tags_list,message.server,message.channel)
            self.scheduler.subscriptions.append(new_sub)
        except Exception as e:
            await self.bot.say('Error while adding sub `{}`'.format(repr(e)))
            raise e
        await self.bot.say('successfully subscribed to the tags: `{}`'.format(tags))


    @dans.command(pass_context=True)
    async def unsub(self, ctx, *, tags):
        raise NotImplemented

    @dans.command(pass_context=True)
    async def list(self, ctx):
        message = ctx.message
        found_subs = ''
        for sub in self.scheduler.subscriptions:
            if message.author in sub.users:
                found_subs += '\n`{}`'.format(sub.tags_to_string())

        if not found_subs == '':
            await self.bot.reply(found_subs)
        else:
            await self.bot.reply('You aren\'t subscribed to any tags')


def setup(bot):
    bot.add_cog(Danbooru(bot))
