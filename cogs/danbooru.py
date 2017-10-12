from discord.ext import commands
import discord
import aiohttp
import json
import os
import datetime
from dateutil import parser
import asyncio
import re
import traceback
from .utils import checks

class Helper:
    def __init__(self, session, bot, auth_file):
        self.bot = bot
        self.session = session
        self.auth_file = auth_file


    async def lookup_pool(self, pool_id):
        with open(self.auth_file) as file:
            data = json.load(file)
            user = data['user']
            api_key = data['api_key']
        auth = aiohttp.BasicAuth(user, api_key)
        url = 'http://danbooru.donmai.us/pools/{}.json'.format(pool_id)
        async with self.session.get(url, auth=auth) as response:
            if response.status == 200:
                json_dump = await response.json()
                return json_dump['name']

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
            else:
                return None

class Dansub:

    def __init__(self, users, tags, pools, server: discord.Server, channel: discord.Channel):
        self.users = list()
        if type(users) == list:
            self.users += users
        else:
            self.users.append(users)
        self.tags = tags
        self.pools = pools
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

    def tags_to_message(self):
        tags_list = self.tags.copy()
        for tag in self.tags:
            if 'pool:' in tag:
                for pool in self.pools:
                    if pool['tag'] == tag:
                        tags_list.remove(tag)
                        tag = '{0[name]}({0[tag]})'.format(pool)
                        tags_list.append(tag)
        return ' '.join(tags_list)






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
        ret_val['pools'] = self.pools
        return json.dumps(ret_val, indent=2)

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
        while not self.bot.is_closed:
            subs_copy = self.subscriptions.copy()
            for sub in subs_copy:
                # skip the subscription if the sub was already removed
                if sub not in self.subscriptions:
                    continue
                new_posts = list()
                timestamp_posted = list()
                try:
                    tags = sub.tags_to_string()
                    images = await self.helper.lookup_tags(tags)
                    # skip if nothing was send back
                    if not images:
                        continue
                    for image in images:
                        created = parser.parse(image['created_at'])
                        if not sub.old_timestamp:
                            sub.old_timestamp = created
                            await self.send_new_posts(sub,[image['file_url']])
                            sub.write_sub_to_file()
                        if created > sub.old_timestamp:
                            new_posts.append(image['file_url'])
                            timestamp_posted.append(created)
                    if new_posts:
                        await self.send_new_posts(sub,new_posts)
                        sub.old_timestamp = max(timestamp_posted)
                        sub.write_sub_to_file()
                    number_subs = len(self.subscriptions)
                    if number_subs < 1800:
                        await asyncio.sleep(1800//number_subs)
                    else:
                        await asyncio.sleep(5)

                except asyncio.CancelledError as e:
                    self.write_to_file()
                    for subscription in self.subscriptions:
                        subscription.write_sub_to_file()
                    await self.bot.send_message(sub.channel, 'Subscription module deactivated')
                    return
                except Exception as e:
                    owner = discord.User(id='134310073014026242')
                    self.write_to_file()
                    for subscription in self.subscriptions:
                        subscription.write_sub_to_file()
                    await self.bot.send_message(owner,
                                                'Error during update Task: `{}`'.format(repr(e)))
                    await self.bot.send_message(owner, 'during Sub: `{}`'.format(sub.tags_to_string()))
                    await self.bot.send_message(owner, '```\n{}\n```'.format(traceback.print_exc()))
                    await self.bot.send_message(sub.channel, 'Error during update Task, deactivating task.')
                    await self.bot.send_message(sub.channel, '{}, Please reload cog'.format(owner.mention))
                    return
            await asyncio.sleep(5)
            self.write_to_file()

    def retrieve_subs(self):
        if not os.path.exists(self.subs_file):
            open(self.subs_file,'w').close()
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
        if 'pools' in data:
            pools = data['pools']
        else:
            pools = []
        retrieved_sub = Dansub(user_list,tags,pools,server,channel)
        if timestamp != 'None':
            retrieved_sub.old_timestamp = parser.parse(timestamp)
        return retrieved_sub


    async def send_new_posts(self, sub, new_posts):
        await self.bot.send_message(sub.channel, sub.users_to_mention())
        await self.bot.send_message(sub.channel, '`{}`'.format(sub.tags_to_message()))
        for post in new_posts:
            await self.bot.send_message(sub.channel, post)
        await self.bot.send_message(sub.channel, '`{}`'.format(sub.tags_to_message()))

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
        self.init_directories()

    def __unload(self):
        self.scheduler.schedule_task.cancel()
        try:
            if not self.scheduler.subscriptions:
                return
            self.scheduler.write_to_file()
            for sub in self.scheduler.subscriptions:
                sub.write_sub_to_file()
                del sub
            self.session.close()
            del self.scheduler
        except Exception as e:
            print(e)
            raise e

    def init_directories(self):
        if not os.path.exists('data/danbooru'):
            os.mkdir('data/danbooru')
        if not os.path.exists('data/danbooru/subs/'):
            os.mkdir('data/danbooru/subs')
        if not os.path.exists(self.auth_file):
            print('authentication file is missing')


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
        resp = await self.helper.lookup_tags(tags, limit='1')

        if not resp:
            await self.bot.say("Error while looking up tag. Try again or correct your tags.")
            return
        timestamp = parser.parse(resp[0]['created_at'])
        tags_list = tags.split(' ')
        pool_list = []
        for tag in tags_list:
            if "pool:" in tag:
                pool_id = tag[len('pool:'):]
                pool_name = await self.helper.lookup_pool(pool_id)
                pool_tag = tag
                pool = {'tag': pool_tag, 'name': pool_name, 'id': pool_id}
                pool_list.append(pool)
        message = ctx.message
        try:
            for sub in self.scheduler.subscriptions:
                if sub.compare_tags(tags_list):
                    for user in sub.users:
                        if user.id == message.author.id:
                            await self.bot.reply('You are already subscribed to those tags')
                            return
                    sub.users.append(message.author)
                    sub.write_sub_to_file()
                    await self.bot.reply('Successfully added to existing sub `{}`'.format(sub.tags_to_message()))
                    return
            new_sub = Dansub(message.author, tags_list, pool_list, message.server, message.channel)
            new_sub.old_timestamp = timestamp
            self.scheduler.subscriptions.append(new_sub)
            new_sub.write_sub_to_file()
        except Exception as e:
            await self.bot.say('Error while adding sub `{}`'.format(repr(e)))
            raise e
        await self.bot.say('successfully subscribed to the tags: `{}`'.format(new_sub.tags_to_message()))
        await self.bot.say('here is the newest image: {}'.format(resp[0]['file_url']))


    @dans.command(pass_context=True)
    async def unsub(self, ctx, *, tags):
        tags_list = tags.split(' ')
        message = ctx.message
        user_unsubscribed = False
        for sub in self.scheduler.subscriptions:
            if sub.compare_tags(tags_list):
                for user in sub.users:
                        if user.id == message.author.id:
                           try:
                                user_unsubscribed = True
                                sub.users.remove(user)
                                self.scheduler.write_to_file()
                                sub.write_sub_to_file()
                                await self.bot.reply('successfully unsubscribed')
                           except Exception as e:
                               await self.bot.say('Error while unsubscribing: `{}`'.format(repr(e)))
                               raise e
                if not user_unsubscribed:
                    await self.bot.reply('You aren\'t subscribed to that tag')
                if not sub.users:
                    try:
                        self.scheduler.subscriptions.remove(sub)
                        os.remove(sub.feed_file)
                        await self.bot.say('subscription fully removed')
                    except Exception as e:
                        await self.bot.say('Error while removing feed file. `{}`'.format(repr(e)))



    @dans.command(pass_context=True)
    async def list(self, ctx):
        message = ctx.message
        found_subs = ''
        for sub in self.scheduler.subscriptions:
            if message.author in sub.users:
                found_subs += '\n`{}`'.format(sub.tags_to_message())

        if not found_subs == '':
            await self.bot.reply(found_subs)
        else:
            await self.bot.reply('You aren\'t subscribed to any tags')

    @dans.command(hidden=True)
    @checks.is_owner()
    async def convert(self):
        with open('data/danbooru/subs_old.db') as file:
            lines = file.readlines()
            if lines:
                for line in lines:
                    sub = line.split('|')
                    await self.bot.say('converting the following sub:`{}`'.format(sub[0]))
                    server = self.bot.get_server(sub[3])
                    channel = self.bot.get_channel(sub[2])
                    users = sub[1].split(';')
                    userlist = []
                    for user in users:
                        if server:
                            member = server.get_member(user)
                        if not member:
                            member = discord.User(id=user)
                        userlist.append(member)

                    tags = sub[0]
                    tags = tags.split(' ')
                    dansub = Dansub(userlist,tags,server,channel)
                    dansub.old_timestamp = parser.parse(sub[4])
                    self.scheduler.subscriptions.append(dansub)
                    dansub.write_sub_to_file()
                self.scheduler.write_to_file()


def setup(bot):
    bot.add_cog(Danbooru(bot))
