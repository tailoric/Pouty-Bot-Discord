from discord.ext import commands, tasks
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
from .utils.paginator import TextPages,FieldPages
from textwrap import shorten
import logging
from os import path
import typing



class DanbooruTypeConverter(commands.Converter):


    async def convert(self, ctx, argument):
        types = {"general": 0, "artist": 1, "copyright": 3, "character": 4, "meta": 5}
        if argument in types.keys():
            return types[argument]
        else:
            raise commands.BadArgument(f"type must be one of the following {','.join(types.keys())}")

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
        url = 'https://danbooru.donmai.us/pools/{}.json'.format(pool_id)
        async with self.session.get(url, auth=auth) as response:
            if response.status == 200:
                json_dump = await response.json()
                return json_dump['name']

    async def lookup_posts(self, limit=200):
        params = {'limit': limit}
        url = 'https://danbooru.donmai.us'
        with open(self.auth_file) as file:
            data = json.load(file)
            user = data['user']
            api_key = data['api_key']
        auth = aiohttp.BasicAuth(user, api_key)
        async with self.session.get('{}/posts.json'.format(url), params=params, auth=auth) as response:
            if response.status == 200:
                json_dump = await response.json()
                for image in json_dump:
                    if not image.get('id'):
                        continue
                    if image['has_large'] and image['file_ext'] == 'zip' and not image.get('is_deleted'):
                        image['file_url'] = self.build_url(url, image['large_file_url']) if image.get('large_file_url') else image.get('source')
                    else:
                        image['file_url'] = self.build_url(url, image['file_url'])
                return json_dump
            else:
                return None

    async def lookup_tags(self, tags, **kwargs):
        params = {'tags' : tags}
        for key, value in kwargs.items():
            params[key] = value
        with open(self.auth_file) as file:
            data = json.load(file)
            user = data['user']
            api_key = data['api_key']
        auth = aiohttp.BasicAuth(user, api_key)
        url = 'https://danbooru.donmai.us'
        async with self.session.get('{}/posts.json'.format(url), params=params, auth=auth) as response:
            if response.status == 200:
                json_dump = await response.json()
                for image in json_dump:
                    if not image.get('id'):
                        continue
                    if image.get('has_large', None) and image.get('file_ext', None) == 'zip' and not image.get('is_deleted'):
                        image['file_url'] = self.build_url(url, image['large_file_url']) if image.get('large_file_url') else image.get('source')
                    elif image.get('file_url', None):
                        image['file_url'] = self.build_url(url, image['file_url'])
                    elif image.get('source', None):
                        image['file_url'] = image.get('source')
                    elif image.get('is_deleted', False) or image.get('is_banned', False):
                        image['file_url'] = None
                    else:
                        image['file_url'] = f"https://danbooru/donmai.us/posts/{image['id']}"
                return json_dump
            else:
                return None

    def build_url(self, base_url: str, file_url: str):
        if file_url.startswith("http"):
            return file_url
        if file_url[0] != "/":
            file_url = "/" + file_url
        return base_url + file_url

class Dansub:

    def __init__(self, users, tags, pools, server: discord.guild, channel: discord.TextChannel, is_private: bool, paused_users=None):
        self.users = list()
        if type(users) == list:
            self.users += users
        else:
            self.users.append(users)
        self.tags = tags
        self.pools = pools
        if not is_private:
            self.guild = server
            self.channel = channel
        self.old_timestamp = None
        self.new_timestamp = datetime.datetime.now()
        self.already_posted = list()
        self.is_private = is_private
        self.feed_file = 'data/danbooru/subs/{}.json'.format(self.tags_to_filename())
        if paused_users:
            self.paused_users = paused_users
        else:
            self.paused_users = []

    # use this one to create private subs

    def users_to_mention(self):
        mention_string = ','.join(user.mention for user in self.users if user.id not in self.paused_users)
        return mention_string

    def tags_to_string(self):
        self.tags.sort()
        return ' '.join(self.tags)

    def compare_tags(self,tags):
        tags.sort()
        return tags == self.tags

    def tags_to_filename(self):
        # delete any character that isn't a word char - _ or . from the filename
        if self.is_private:
            return re.sub('[^\w\-_\.]','_', self.tags_to_string()) + str(self.users[0].id)
        else:
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
        ret_val['is_private'] = self.is_private
        if not self.is_private:
            ret_val['server'] = self.guild.id
            ret_val['channel'] = self.channel.id
        ret_val['old_timestamp'] = str(self.old_timestamp)
        ret_val['new_timestamp'] = str(self.new_timestamp)
        ret_val['already_posted'] = self.already_posted
        ret_val['pools'] = self.pools
        ret_val['paused_users'] = []
        for paused_user in self.paused_users:
            ret_val['paused_users'].append(paused_user)
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
        self.helper = Helper(self.session, self.bot, self.auth_file)
        self.logger = logging.getLogger('discord')

    @tasks.loop(minutes=1)
    async def schedule_task(self):
        #iterate through all subscriptions and update information
        subs_copy = self.subscriptions.copy()
        for sub in subs_copy:
            # skip the subscription if the sub was already removed
            if sub not in self.subscriptions:
                continue
            if sub.is_private and len(sub.paused_users) > 0 or len(sub.paused_users) == len(sub.users):
                continue
            try:
                images = await self.helper.lookup_tags(sub.tags_to_string())
                if not images:
                    continue
                new_posts, timestamp_posted = await self._find_all_new_posts(images, sub)
                if new_posts:
                    await self.send_new_posts(sub, new_posts)
                    sub.old_timestamp = max(timestamp_posted)
                    sub.write_sub_to_file()
                await asyncio.sleep(30)

            except asyncio.CancelledError as e:
                self._write_subs_information_to_file()
                raise
            except aiohttp.ClientOSError as cle:
                self._write_subs_information_to_file()
                await asyncio.sleep(10)
                continue
            except Exception as e:
                owner = self.bot.get_user(134310073014026242)
                self._write_subs_information_to_file()
                message = ('Error during update Task: `{}`\n'
                           'during Sub: `{}`\n'
                           '```\n{}\n```'
                           .format(repr(e),sub.tags_to_string(),traceback.format_exc()))
                await owner.send(message)
                await asyncio.sleep(10)
                continue
        self.write_to_file()

    def cancel_task(self):
        self.schedule_task.cancel()

    def _write_subs_information_to_file(self):
        self.write_to_file()
        for subscription in self.subscriptions:
            subscription.write_sub_to_file()

    async def _find_all_new_posts(self, images, sub):
        new_posts = list()
        timestamp_posted = list()
        if not images:
            return
        for image in images:
            if not image.get('file_url'):
                continue
            created = parser.parse(image['created_at'])
            if not sub.old_timestamp:
                sub.old_timestamp = created
                await self.send_new_posts(sub,[image['file_url']])
                sub.write_sub_to_file()
            if created > sub.old_timestamp:
                new_posts.append(image['file_url'])
                timestamp_posted.append(created)
        return new_posts,timestamp_posted

    def retrieve_subs(self):
        if not os.path.exists(self.subs_file):
            open(self.subs_file,'w').close()
        with open(self.subs_file) as f:
            lines = f.readlines()
        for line in lines:
            line = line.replace('\n','')
            line = line.replace('\'','')
            sub = self.create_sub_from_file(line)
            if sub == None:
                continue
            print(sub.tags_to_string())
            self.subscriptions.append(sub)

    def create_sub_from_file(self,json_path):
        with open(json_path) as sub_file:
            data = json.load(sub_file)

        user_list = []

        if 'is_private' in data and bool(data['is_private']):
            is_private = True
            id = data['users']['0']['id']
            name = data['users']['0']['name']
            user = self.bot.get_user(id)
            if user is None:
                return None
            user_list.append(user)
        else:
            is_private = False
            if os.path.exists('data/danbooru/sub_channel.json'):
                with open('data/danbooru/sub_channel.json','r') as f:
                    sub_channel_file = json.load(f)
                server = self.bot.get_guild(int(sub_channel_file['server']))
                channel = self.bot.get_channel(int(sub_channel_file['channel']))
            else:
                server = self.bot.get_guild(int(data['server']))
                channel = self.bot.get_channel(int(data['channel']))
            for user in data['users']:
                # try to get the member through Discord and their ID
                member = server.get_member(int(data['users'][user]['id']))
                # if that fails create own user with the necessary information
                if member == None:
                    continue
                user_list.append(member)

        tags = data['tags']
        timestamp = data['old_timestamp']
        if 'paused_users' in data:
            paused_users = data['paused_users']
        else:
            paused_users = []
        if 'pools' in data:
            pools = data['pools']
        else:
            pools = []
        if is_private:
            retrieved_sub = Dansub(user_list, tags, pools, None, None, is_private, paused_users)
        else:
            retrieved_sub = Dansub(user_list, tags, pools, server, channel, is_private, paused_users)
        if timestamp != 'None':
            retrieved_sub.old_timestamp = parser.parse(timestamp)
        return retrieved_sub

    async def send_new_posts(self, sub, new_posts):
        message_list = self._split_message_in_groups_of_four(sub, new_posts)
        for partial_message in message_list:
            if sub.is_private:
                try:
                    await sub.users[0].send(partial_message)
                except discord.Forbidden:
                    self.subscriptions.remove(sub)
                    self.write_to_file()
                    os.remove(sub.feed_file)
                    self.logger.warning("Could not DM user, deleting private sub: %s", sub.tags_to_string(),exc_info=True)
            else:
                await sub.channel.send(partial_message)
            await asyncio.sleep(10)

    def find_matching_subs(self, tags, subs, image):
        matched_subs = list()
        for sub in subs:
            if sub.tags_to_string() in image['tag_string']:
                matched_subs.append(sub.users)
        return matched_subs

    def _split_message_in_groups_of_four(self, sub, new_posts):
        message_list = []
        message = ('{}\n'
                   '`{}`\n'
                   .format(sub.users_to_mention(),sub.tags_to_message()))
        for index, post in enumerate(new_posts,1):
            if index%4 == 0:
                if post is new_posts[-1]:
                    break
                message_list.append(message)

                message = ""
            message += post + "\n"
        message += ('`{}`'.format(sub.tags_to_message()))
        message_list.append(message)
        return message_list


    def _reduce_message_spam(self, sub, new_posts):
        message_list = []
        message = ('{}\n'
                   '`{}`\n'
                   .format(sub.users_to_mention(),sub.tags_to_message()))
        for post in new_posts:
            if len(message + post + '\n') > 2000:
                message_list.append(message)
                message = ""
            message += post+'\n'
        message_list.append(message)
        return message_list


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



class Danbooru(commands.Cog):
    """
    Danbooru related commands
    """
    def __init__(self, bot):
        self.bot = bot
        self.auth_file = 'data/danbooru/danbooru.json'
        self.session = aiohttp.ClientSession()
        self.scheduler = Scheduler(self.bot,self.session)
        self.running_task = self.scheduler.schedule_task.start()
        self.helper = Helper(self.session,self.bot,self.auth_file)
        self.init_directories()
        self.blacklist_tags_file = 'data/danbooru_cog_blacklist.json'
        self.danbooru_channel_file = 'data/danbooru_channel_file.json'
        self.bucket = commands.CooldownMapping.from_cooldown(1, 60, commands.BucketType.member)
        with open(self.blacklist_tags_file, 'r') as f:
            self.tags_blacklist = json.load(f)
        if path.exists(self.danbooru_channel_file):
            with open(self.danbooru_channel_file, 'r') as file:
                self.danbooru_channels = json.load(file)
        else:
            self.danbooru_channels = []

    async def cog_unload(self):
        try:
            self.running_task.cancel()
            if not self.scheduler.subscriptions:
                return
            self.scheduler.write_to_file()
            for sub in self.scheduler.subscriptions:
                sub.write_sub_to_file()
                del sub
            self.bot.loop.create_task(self.session.close())
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

    def _add_blacklist_to_tags(self, tags):
        if self.tags_blacklist:
            blacklist = ' -'+' -'.join(self.tags_blacklist)
            tags += blacklist
        return tags

    @checks.is_owner_or_moderator()
    @commands.group(pass_context=True, aliases=['danbl'])
    async def blacklist_tags(self, ctx):
        """
        danbooru blacklist tags (use .help danbl for more info)
        use .danbl add for adding tags to the blacklist
        use .danbl remove/del/rm for removing tags from the blacklist
        """
        if ctx.invoked_subcommand is None:
            await ctx.send("Following tags are blacklisted"
                               "```\n"
                               +'\n'.join(self.tags_blacklist)
                               +"```")


    @blacklist_tags.command(aliases=['add'])
    async def blacklist_add(self, ctx, tag):
        """adds a tag to the danbooru tag blacklist"""
        self.tags_blacklist.append(tag)
        with open(self.blacklist_tags_file, 'w') as f:
            json.dump(self.tags_blacklist, f)
        await ctx.send("tag `{0}` added".format(tag))


    @blacklist_tags.command(aliases=['remove', 'del', 'rm'])
    async def blacklist_remove(self, ctx, tag):
        """removes a tag from the danbooru tag blacklist"""
        try:
            self.tags_blacklist.remove(tag)
        except ValueError:
            await ctx.send("tag not in blacklist")
            return
        with open(self.blacklist_tags_file, 'w') as f:
            json.dump(self.tags_blacklist, f)
        await ctx.send("tag `{0}` removed".format(tag))

    @blacklist_tags.command(aliases=['list'])
    async def blacklist_list(self, ctx):
        await ctx.send("Following tags are blacklisted"
                           "```\n"
                           +'\n'.join(self.tags_blacklist)
                           +"```")

    @commands.command(pass_context=True)
    @checks.is_owner_or_moderator()
    async def setup_dan(self, ctx):

        if len([x['channel'] for x in self.danbooru_channels if x['channel'] == ctx.message.channel.id]) > 0:
            await ctx.send("channel already setup")
            return

        self.danbooru_channels.append({
            'channel': ctx.message.channel.id,
            'server': ctx.message.guild.id
        })
        with open(self.danbooru_channel_file,  'w') as f:
            json.dump(self.danbooru_channels, f)
        await ctx.send("channel setup for danbooru commands")

    def _get_danbooru_channel_of_message(self,message : discord.Message):
        server = message.guild
        danbooru_channel = [x["channel"] for x in self.danbooru_channels if int(x["server"])== server.id]
        if danbooru_channel:
            return self.bot.get_channel(int(danbooru_channel[0]))
        else:
            return None

    async def _find_danbooru_image(self, ctx, tags, random):
        if any(tag in self.tags_blacklist for tag in tags.split()):
            await ctx.send("You used a blacklisted tag, please don't use these.")
            return None, None 
        message = ctx.message
        if ctx.guild:
            channel = self._get_danbooru_channel_of_message(message)
            if channel is None:
                await ctx.send("danbooru channel not setup")
                return
        else:
            channel = ctx.message.channel
        tags = self._add_blacklist_to_tags(tags)
        if random:
            image = await self.helper.lookup_tags(tags, limit='1', random=random)
        else:
            image = await self.helper.lookup_tags(tags, limit='1')
        if not image or len(image) == 0:
            await ctx.send("no image found please refer to the pin:\n"
                           "https://discordapp.com/channels/187423852224053248/402151326915493888/582629178285883394\n"
                           "or use the `dantag` command with part of the character or franchise name to see how it"
                           " is written correctly")
            return None, None
        return channel, self.build_message(image, channel, message)

    @commands.command(name="dant", aliases=["dantag", "dan_tag"], usage="tagname category=[general, artist, copyright, character, meta]")
    async def dan_tag(self, ctx, tag, category: typing.Optional[DanbooruTypeConverter]):
        """Searches danbooru for matching tags
           category can be either of those [general, artist, copyright, character, meta]
           examples:
                .dantag eyes general (to search tags of the geneeral category containing the name 'eyes')
                .dantag fate copyright (to search franchises containing the name 'fate')
           """
        types = {0: "general",  1: "artist",  3: "copyright", 4: "character", 5: "meta"}
        url = f"https://danbooru.donmai.us/tags.json?search[hide_empty]=yes&search[order]=count&search[name_matches]=*{tag}*"
        if category:
            url += f"&search[category]={category}"
        entries = []
        async with self.session.get(url) as resp:
            if resp.status == 200:
                info = (await resp.json())
                for tag in info:
                    related_tags = tag.get('related_tags', '')
                    tag_name = tag.get('name', None)
                    value = '\u200b'
                    if related_tags:
                        related_tags_list = related_tags.split()
                        related_tags_list = [t for t in related_tags_list if not t.isdigit()]
                        related_tags_list = [t for t in related_tags_list if not re.fullmatch(r'\d+\.\d+', t)]
                        if tag_name in related_tags_list:
                            related_tags_list.remove(tag_name)
                        related_tags = ', '.join(related_tags_list)
                        related_tags = discord.utils.escape_markdown(related_tags)
                        value = f"**related tags**: {related_tags}"
                    tag_name = discord.utils.escape_markdown(tag_name)
                    key = f"{tag_name} [{types[tag['category']]}]"
                    entries.append((key, value))
                if entries:
                    pages = FieldPages(ctx, entries=entries, per_page=5)
                    await pages.paginate()
                else:
                    await ctx.send("Nothing found")





    @commands.group(invoke_without_command=True)
    async def dan(self, ctx, *, tags: str = ""):
        """
        display newest image from danbooru with certain tags
        tags: tags that will be looked up.
        """
        channel, send_message = await self._find_danbooru_image(ctx, tags, random=None)
        if channel is None or send_message is None:
            return
        await channel.send(send_message)

    @dan.command(name="def", aliases=["definition", "wiki"])
    async def def_(self, ctx, tag):
        async with self.session.get(f"https://danbooru.donmai.us/wiki_pages.json?search[title]={tag}") as resp:
            if resp.status == 200:
                info = (await resp.json())[0]
                title = info.get("title", tag)
                description = info.get("body")
                description_clean = discord.utils.escape_markdown(description)
                embed = discord.Embed(title=title,
                                      url=f"https://danbooru.donmai.us/wiki_pages?title={title}",
                                      description=shorten(description_clean, 2040)
                                      )
                if info.get("other_names", None):
                    embed.add_field(name="Other Names", value="\n".join(info["other_names"]))
                await ctx.send(embed=embed)
            elif resp.status == 404:
                await ctx.send("tag not found")
            else:
                await ctx.send(f"Danbooru replied with following code: {resp.status}")


    @commands.command(name="danu", aliases=["danundo", "dundo", "dan_undo", "danremove", "danrm"])
    @commands.guild_only()
    async def dan_undo(self, ctx, message: typing.Optional[discord.Message], number: typing.Optional[int]):
        """removes the last image or the last x images you requested from the bot"""
        if ctx.channel.id not in [d["channel"] for d in self.danbooru_channels]:
            return await ctx.send("Please use the command in the danbooru channel")
        deleted_counter = 0
        if message and message.author == message.guild.me and "http" in message.content:
            await message.delete()
            return await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")
        elif number:
            messages = [m async for m in ctx.channel.history(limit=100, before=ctx.message)]
            to_delete = []
            for index, msg in enumerate(messages):
                if msg.author.id == ctx.author.id and "http" in messages[index -1].content:
                    to_delete.append(messages[index-1])
                    deleted_counter += 1
                    if not number and deleted_counter == 1:
                        break
                    elif number <= deleted_counter:
                        break
            await ctx.channel.delete_messages(to_delete)
            await ctx.send(f"Deleted {deleted_counter} images", delete_after=5)
        elif not number and not message:
            replied = ctx.message.reference
            if not replied:
                await ctx.send("No valid message specified")
            elif isinstance(replied.resolved, discord.Message):
                await replied.resolved.delete()
                return await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")
            else:
                return await ctx.send("Could not fetch reply")

    @commands.command(pass_context=True)
    async def danr(self, ctx, *, tags: str = ""):
        """
        display random image from danbooru with certain tags
        tags: tags that will be looked up.
        """
        channel, send_message = await self._find_danbooru_image(ctx, tags, random="true")
        if channel is None or send_message is None:
            return
        await channel.send(send_message)


    @commands.group(pass_context=True, hidden=True)
    async def dans(self, ctx):
        """
        Danbooru subscribing service
        """
        if ctx.invoked_subcommand is None:
            await ctx.send("invalid command use `.help dans`")

    @dans.command(pass_context=True)
    async def sub(self, ctx, *, tags):
        """
        subscribe to provided tags
        tags: tags that will be looked up
        """
        resp = await self.helper.lookup_tags(tags, limit='1')

        if not resp:
            await ctx.send("Error while looking up tag. Try again or correct your tags.")
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
        is_private = type(ctx.message.channel) is discord.DMChannel
        try:
            for sub in self.scheduler.subscriptions:
                if sub.compare_tags(tags_list) and (not sub.is_private or is_private):
                    for user in sub.users:
                        if user.id == message.author.id:
                            await ctx.send('{}\nYou are already subscribed to those tags'.format(ctx.message.author.mention))
                            return
                    if sub.is_private or is_private:
                        break
                    sub.users.append(message.author)
                    sub.write_sub_to_file()
                    await ctx.send('{}\nSuccessfully added to existing sub `{}`'.format(ctx.message.author.mention,sub.tags_to_message()))
                    return
            if os.path.exists('data/danbooru/sub_channel.json'):
                with open('data/danbooru/sub_channel.json') as f:
                    data = json.load(f)
                    server = self.bot.get_guild(int(data['server']))
                    channel = self.bot.get_channel(int(data['channel']))
                new_sub = Dansub(message.author, tags_list, pool_list, server, channel, is_private)
            else:
                new_sub = Dansub(message.author, tags_list, pool_list, message.guild, message.channel,is_private)

            new_sub.old_timestamp = timestamp
            self.scheduler.subscriptions.append(new_sub)
            new_sub.write_sub_to_file()
        except Exception as e:
            await ctx.send('Error while adding sub `{}`'.format(repr(e)))
            raise e
        await ctx.send('successfully subscribed to the tags: `{}`'.format(new_sub.tags_to_message()))
        await ctx.send('here is the newest image: {}'.format(resp[0]['file_url']))


    @dans.command(pass_context=True)
    async def unsub(self, ctx, *, tags):
        """
        unsubscribe from subscription
        tags:
        """
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
                                await ctx.send("successfully unsubscribed")
                           except Exception as e:
                               await ctx.send('Error while unsubscribing: `{}`'.format(repr(e)))
                               raise e
                if not user_unsubscribed:
                    await ctx.send('You aren\'t subscribed to that tag')
                if not sub.users:
                    try:
                        self.scheduler.subscriptions.remove(sub)
                        os.remove(sub.feed_file)
                        await ctx.send('subscription fully removed')
                    except Exception as e:
                        await ctx.send('Error while removing feed file. `{}`'.format(repr(e)))

    @dans.command(pass_context=True)
    async def pause(self, ctx):
        """
        pauses all subscriptions that are currently running
        """
        subscriber = ctx.message.author
        subscriptions_of_user = [sub for sub in self.scheduler.subscriptions if subscriber in sub.users]
        for subscription in subscriptions_of_user:
            subscription.paused_users.append(subscriber.id)
            subscription.write_sub_to_file()
        await ctx.send("paused all of your subscriptions")

    @dans.command(pass_context=True)
    async def unpause(self, ctx):
        """
        un-pauses all paused subscription
        """
        subscriber = ctx.message.author
        subscriptions_of_user = [sub for sub in self.scheduler.subscriptions if subscriber in sub.users]
        for subscription in subscriptions_of_user:
            if int(subscriber.id) in subscription.paused_users:
                subscription.paused_users.remove(int(subscriber.id))
            subscription.write_sub_to_file()
        await ctx.send("unpaused all of your subscriptions")

    @dans.command(pass_context=True)
    async def list(self, ctx):
        """
        list all subscribed tags
        """
        message = ctx.message
        found_subs = ''
        one_sub_found = False
        for sub in self.scheduler.subscriptions:
            if message.author in sub.users and (not sub.is_private or isinstance(message.channel, discord.DMChannel)):
                if sub.is_private:
                    found_subs += '[private] {}\n'.format(sub.tags_to_string())
                else:
                    found_subs += '{}\n'.format(sub.tags_to_message())
                one_sub_found = True
        if one_sub_found:
            pages = TextPages(ctx, found_subs)
            await pages.paginate()
        else:
            await ctx.send('You aren\'t subscribed to any tags')

    @dans.command(hidden=True)
    @checks.is_owner()
    async def convert(self, ctx):
        with open('data/danbooru/subs_old.db') as file:
            lines = file.readlines()
            if lines:
                for line in lines:
                    sub = line.split('|')
                    await ctx.send('converting the following sub:`{}`'.format(sub[0]))
                    server = self.bot.get_guild(sub[3])
                    channel = self.bot.get_channel(sub[2])
                    users = sub[1].split(';')
                    userlist = []
                    for user in users:
                        if server:
                            member = server.get_member(user)
                        if not member:
                            member = self.bot.get_user(user)
                        userlist.append(member)

                    tags = sub[0]
                    tags = tags.split(' ')
                    dansub = Dansub(userlist,tags,server,channel)
                    dansub.old_timestamp = parser.parse(sub[4])
                    self.scheduler.subscriptions.append(dansub)
                    dansub.write_sub_to_file()
                self.scheduler.write_to_file()


    @dans.command(hidden=True, pass_context=True)
    @checks.is_owner()
    async def setup(self, ctx):
        message = ctx.message
        server = message.guild
        channel = message.channel
        with open('data/danbooru/sub_channel.json', 'w') as f:
           input = {
               'server': server.id,
               'channel': channel.id
               }
           json.dump(input,f)
        await ctx.send('channel setup for subscription')

    @dans.command()
    async def restart(self, ctx):
        """
        ONLY USE WHEN STUCK!
        """
        await self.bot.reload_extension("cogs.danbooru")
        await ctx.message.add_reaction("\N{THUMBS UP SIGN}")

    def build_message(self, image, channel, message):

        file_url = image[0]['file_url']
        send_message = file_url
        if 'translated' in image[0]['tag_string_meta']:
            send_message = 'https://danbooru.donmai.us/posts/' + str(image[0]['id'])
        if 'spoilers' in image[0]['tag_string_meta']:
            send_message = "`({0})`|| {1} ||".format(image[0]['tag_string_copyright'], send_message)
        if not channel.id == message.channel.id:
            send_message = '{0}\n{1}'.format(send_message, message.author.mention)

        return send_message


async def setup(bot):
    await bot.add_cog(Danbooru(bot))
