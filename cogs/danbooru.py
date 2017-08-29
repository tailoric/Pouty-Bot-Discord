from discord.ext import commands
import discord
import aiohttp
import json
import os
import datetime
from dateutil import parser
from .utils import checks
import asyncio
from asyncio import Lock
import time

class Dansub:
    def __init__(self,bot, session, server, user, channel, tags):
        self.bot = bot
        self.session = session
        self.server = server
        self.users = list()
        if type(user) == list:
            self.users += user
        else:
            self.users.append(user)
        self.channel = channel
        self.tags = tags
        self.timestamp = datetime.datetime
        self.auth_file = 'data/danbooru/danbooru.json'
        self.feed_file = self.file_name(self.users[0], self.tags)
        self.update_loop = None

    def __str__(self):
        user_ids = [i.id for i in self.users]
        user_string = ';'.join(user_ids)
        return "{0}|{1}|{2.id}|{3.id}|{4}\n".format(self.tags, user_string, self.channel, self.server, str(self.timestamp))

    def add_user(self,user):
        self.users.append(user)

    def set_timestamp(self,timestamp):
        self.timestamp = parser.parse(timestamp)

    def file_name(self,user,tags):
        fmt = 'data/danbooru/subs/{0}.txt'
        tag_names = tags.replace(' ','_').replace(':','')
        return fmt.format(tag_names)

    def compare_tags(self, tags):
        my_tags = self.tags.split()
        my_tags.sort()
        other_tags = tags.split()
        other_tags.sort()
        return my_tags == other_tags

    async def update_feed(self):
        while not self.bot.is_closed:
            images = await self.lookup_tag(self.tags)
            timestamp_posted = list()
            new_posts = list()
            for image in images:
                created = parser.parse(image['created_at'])
                if created > self.timestamp:
                    timestamp_posted.append(created)
                    new_posts.append(image['file_url'])
            if timestamp_posted:
                self.timestamp = max(timestamp_posted)
                for user in self.users:
                    await self.bot.send_message(self.channel, user.mention)
                await self.bot.send_message(self.channel,'**Tags:** ' + self.tags + '\n')
                await self.bot.send_message(self.channel,(len('Tags: ')+len(self.tags))*'-' + '\n')
                for post in new_posts:
                    await self.bot.send_message(self.channel,post)
                await self.bot.send_message(self.channel,(len('Tags: ')+len(self.tags))*'-' + '\n')
                await self.bot.send_message(self.channel,'**Tags:** ' + self.tags + '\n')
                with open(self.feed_file,'w') as f:
                    f.write(str(self.timestamp))
            await asyncio.sleep(1800)

    async def first_run(self):
        images = await self.lookup_tag(self.tags, limit='3')
        timestamps = list()
        for image in images:
            new_timestamp = parser.parse(image['created_at'])
            timestamps.append(new_timestamp)
            await self.bot.say(image['file_url'])
        if timestamps:
            self.timestamp = max(timestamps)
            with open(self.feed_file,'w') as f:
                output = str(self.timestamp)
                f.write(output)
                self.update_loop = self.bot.loop.create_task(self.update_feed())

    def create_update_task(self):
        self.update_loop = self.bot.loop.create_task(self.update_feed())

    async def lookup_tag(self,tags, **kwargs):
        params = {'tags' : tags}
        for key in kwargs:
            params[key] = kwargs[key]

        with open(self.auth_file, 'r') as file:
            data = json.load(file)
            user = data['user']
            api_key = data['api_key']
        auth = aiohttp.BasicAuth(user, api_key)
        url = 'http://danbooru.donmai.us/'
        async with self.session.get('{}posts.json'.format(url),params=params,auth=auth) as response:
            if response.status == 200:
                json_dump = await response.json()
                if json_dump:
                    for key in json_dump:
                        key['file_url'] = url + key['file_url']
                    return  json_dump
                else:
                    await self.bot.say('empty Server response')
            else:
                await self.bot.say('Danbooru server answered with error code:\n```\n{}\n```'.format(response.status))
class Danbooru:

    def __init__(self, bot):
        self.bot = bot
        self.danbooru_session = aiohttp.ClientSession()
        self.auth_file = 'data/danbooru/danbooru.json'
        self.dansubs = set()
        self.subs_channel = discord.Channel
        self.subs_db = 'data/danbooru/subs.db'
        self.retrieve_subs()

    def __unload(self):
        with open(self.subs_db, 'w') as f:
            while self.dansubs:
                sub = self.dansubs.pop()
                f.write(str(sub))
                if sub.update_loop:
                    sub.update_loop.cancel()
                del sub
            del self.dansubs
        self.danbooru_session.close()

    async def delete_sub(self,sub):
        try:
            if sub.update_loop:
                sub.update_loop.cancel()
            self.dansubs.remove(sub)
            os.remove(sub.feed_file)
            with open(self.subs_db,'w') as f:
                for item in self.dansubs:
                    f.write(str(item))
            await self.bot.reply('unsubbed successfully')
        except Exception as e:
            await self.bot.reply("something went wrong while deleting")

    async def create_update_tasks(self):
        for sub in self.dansubs:
            sub.create_update_task()
            await asyncio.sleep(60)

    def retrieve_subs(self):
        if not os.path.isfile(self.subs_db):
            open(self.subs_db,'w').close()
        else:
            with open(self.subs_db, 'r') as file:
                lines = file.readlines()
                if lines:
                    for line in lines:
                        sub = line.split('|')
                        server = self.bot.get_server(sub[3])
                        channel = self.bot.get_channel(sub[2])
                        users = sub[1].split(';')
                        userlist = []
                        for user in users:
                            userlist.append(server.get_member(user))
                        tags = sub[0]
                        dansub = Dansub(self.bot,self.danbooru_session,server,userlist,channel,tags)
                        with open(dansub.file_name(userlist[0],tags)) as f:
                            dansub.set_timestamp(f.read())
                        self.dansubs.add(dansub)
                    for i in self.dansubs:
                        users_str = str(i.users[0])
                        for user in i.users[1:]:
                            users_str += ', ' + str(user)
                        print('{0.tags} {1};'.format(i, users_str))
                    self.bot.loop.create_task(self.create_update_tasks())

    async def lookup_tag(self,tags, **kwargs):
        params = {'tags' : tags}
        for key in kwargs:
            params[key] = kwargs[key]

        with open(self.auth_file, 'r') as file:
            data = json.load(file)
            user = data['user']
            api_key = data['api_key']
        auth = aiohttp.BasicAuth(user, api_key)
        url = 'http://danbooru.donmai.us/'
        async with self.danbooru_session.get('{}posts.json'.format(url),params=params,auth=auth) as response:
            if response.status == 200:
                json_dump = await response.json()
                if json_dump:
                    for key in json_dump:
                        key['file_url'] = url + key['file_url']
                    return  json_dump
                else:
                    await self.bot.say('empty Server response')
            else:
                await self.bot.say('Danbooru server answered with error code:\n```\n{}\n```'.format(response.status))




    @commands.command()
    async def dan(self,*,tags:str):
        """
        look for the most recent image on danbooru with specified tags
        """
        images = await self.lookup_tag(tags,limit='1')
        await self.bot.say(images[0]['file_url'])

    @commands.command()
    async def danr(self,*,tags:str):
        """
        look for a random image on danbooru with specified tags
        """
        images = await self.lookup_tag(tags, limit='1', random='true')
        await self.bot.say(images[0]['file_url'])

    @commands.group(pass_context=True)
    async def dans(self,ctx):
        '''
        danbooru subscribing service
        use .help dans for more info
        '''
        if ctx.invoked_subcommand is None:
            await self.bot.say('Invalid dans command passed ')

    @dans.command(pass_context=True)
    async def sub(self,ctx, *, tags):
        '''
        subscribe to a number of tags
        '''
        server = ctx.message.server
        channel = ctx.message.channel
        member = ctx.message.author
        for sub in self.dansubs:
            if sub.compare_tags(tags) and ctx.message.author in sub.users:
                await self.bot.reply('these tags are already subbed')
                return
            elif sub.compare_tags(tags) and not ctx.message.author in sub.users:
                sub.add_user(member)
                with open(self.subs_db, 'w') as f:
                    lines = list()
                    for sub in self.dansubs:
                        lines.append(str(sub))
                    f.writelines(lines)
                await self.bot.say('user added to existing sub')
                return
        dansub = Dansub(self.bot,self.danbooru_session,server,member,channel,tags)
        self.dansubs.add(dansub)
        await dansub.first_run()
        with open(self.subs_db, 'a+') as file:
            file.write(str(dansub))

    @dans.command(pass_context=True)
    async def preview(self,ctx, *, tags):
        '''
        see up to three random images from the tags
        '''
        message = await self.bot.say('fetching three random results please wait...')
        images = await self.lookup_tag(tags, limit='3', random='true')
        for image in images:
            await self.bot.say(image['file_url'])
        await self.bot.delete_message(message)

    @dans.command(pass_context=True)
    async def unsub(self,ctx, *, tags):
        '''
        unsubscribe from tags
        '''
        sub_found = False
        for sub in self.dansubs:
            if sub.compare_tags(tags) and ctx.message.author in sub.users:
                sub_found = True
                if len(sub.users) > 1:
                    sub.users.remove(ctx.message.author)
                    with open(self.subs_db, 'w') as f:
                        lines = list()
                        for sub in self.dansubs:
                            lines.append(str(sub))
                        f.writelines(lines)
                    await self.bot.say('successfully unsubscribed')
                else:
                    await self.delete_sub(sub)
        if not sub_found:
            await self.bot.reply('you are not subscribed to that tag')


    @dans.command(pass_context=True,hidden=True)
    @checks.is_owner()
    async def setup(self,ctx):
        self.subs_channel = ctx.message.channel
        channel_file = 'data/danbooru/channel.txt'
        with open(channel_file, 'w') as file:
            file.write(ctx.message.channel.id)
        await self.bot.say('setup complete')
def setup(bot):
    bot.add_cog(Danbooru(bot))
