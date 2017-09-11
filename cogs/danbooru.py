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

    def __init__(self):
        self.users = list()
        self.tags = list()
        self.server = discord.Server()
        self.channel = discord.Channel()
        self.first_timestamp = datetime.datetime
        self.last_timestamp = datetime.datetime

    def tags_to_string(self):
        return ' '.join(self.tags)


class Scheduler:
    def __init__(self, bot, session):
        self.bot = bot
        self.session = session
        self.schedule_task = None
        self.subscriptions = list()
        self.auth_file = 'data/danbooru/danbooru.json'

    async def schedule_task(self):
        #TODO iterate through all subscriptions and update information
        sub_copy = self.subscriptions.copy()
        for sub in sub_copy:
            tags = sub.tags_to_string()
            images = await self.lookup_tags(tags)
            for image in images:
                self.find_other_user(tags,sub_copy,image)


    def find_other_user(self, tags, subs, image):
        for sub in subs:
            if sub.tags_to_string() in image['tag_string']:
                pass

    async def lookup_tags(self, tags, **kwargs):
        params = {'tags' : tags}
        for key in kwargs:
            params[key] = kwargs[key]
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

    def sort_tags(self, image):
        tags = image['tag_string'].split(' ')
        tags.sort()
        sorted_tags = ' '.join(tags)
        image['tag_string'] = sorted_tags




class Danbooru:
    def __init__(self, bot):
        self.bot = bot

    @commands.group(pass_context=True)
    async def dans(self, ctx):
        '''
        Danbooru subscribing service
        '''
        if ctx.invoked_subcommand is None:
            await self.bot.say("invalid command use `.help dans`")

    @dans.command(pass_context=True)
    async def sub(self, ctx):
        raise NotImplemented

    @dans.command(pass_context=True)
    async def unsub(self, ctx):
        raise NotImplemented


def setup(bot):
    bot.add_cog(Danbooru(bot))
