import discord
from discord.ext import commands, tasks
from .utils.checks import is_owner_or_moderator
from datetime import datetime, timedelta, timezone
from logging import getLogger
import json
from pathlib import Path
import io
import textwrap
import asyncio
import re


green = 0x76d16a
red = 0xd16a76
LOOP_TIME = 30 * 60 # 30 minutes
class Thread(commands.Cog):
    """
    A cog for creating "Thread" channels for spoiler discussions etc.
    """
    thread_rule = """
    This channel is for the topic `{}`.
    You don't need to spoiler tag anything that was revealed up to the episode or chapter provided by the topic.
    However spoiler tag everything that is from a different franchise or story or was not covered yet by the current episode/chapter
    """
    topic = """
    Feel free to discuss spoilers or other topics without needing spoiler tags,
    (if this channel was created for an episode/chapter, then only untagged spoilers up to that episode/chapter).
    if someone is not behaving then report it to the moderators.
    """
    def __init__(self, bot):
        self.bot = bot
        self.logger= getLogger("PoutyBot")
        self.admin_cog = self.bot.get_cog("Admin")
        self.check_activity.start()
        self.settings_path = Path('config/thread_channel_settings.json')
        self.scheduled_tasks = []
        if self.settings_path.exists():
            with self.settings_path.open('r') as f:
                self.settings = json.load(f)
                self.attachments_backlog = self.bot.get_channel(self.settings.get("attachments_backlog"))
        else:
            with self.settings_path.open(mode='w') as f:
                self.settings = {
                        "category_channel": None,
                        "join_reaction" : "\N{OPEN LOCK}",
                        "attachments_backlog": None,
                        "livetime": 24,
                        "thread_list_channel": None,
                        }
                json.dump(self.settings,f)

        self.create_thread_table = self.bot.loop.create_task(self.create_thread_log())
        self.create_thread_table = self.bot.loop.create_task(self.create_discord_thread_log())

    async def get_attachment_links(self, message):
        attachment_string_format = "\t[attachments: {}]\n" 
        if not self.attachments_backlog:
            urls = [a.url for a in message.attachments]
            return attachment_string_format.format(','.join(urls)) if urls else ""
        attachment_list = []
        for attach in message.attachments:
            if attach.size > self.attachments_backlog.guild.filesize_limit:
                attach.url += "(FILE TOO BIG)" 
                attachment_list.append(attach)
                continue
            img = io.BytesIO()
            await attach.save(img)
            reupload = await self.attachments_backlog.send(file=discord.File(img, filename=attach.filename))
            attachment_list.extend(reupload.attachments)
        urls = [a.url for a in attachment_list]
        return attachment_string_format.format(','.join(urls))if attachment_list else ""


    async def generate_file(self, channel):
        f = io.StringIO()
        async for message in channel.history(limit=None, oldest_first=True):
            attachments = await self.get_attachment_links(message)
            time_and_author = f"{message.created_at.strftime('%Y-%m-%d %H:%M:%S %Z')} @{message.author}: "
            indent_len = len(time_and_author)
            lines = textwrap.fill(message.clean_content, width=120).splitlines(True)
            if lines:
                first_line = f"{time_and_author}{lines[0]}"
                the_rest = textwrap.indent(''.join(lines[1:]), indent_len * ' ')
                f.write(f"{first_line}{the_rest}\n"
                        f"{attachments}")
            elif attachments:
                f.write(f"{time_and_author}\n{attachments}")
        f.seek(0)
        return f

    def cog_unload(self):
        self.check_activity.cancel()
        for task in self.scheduled_tasks:
            task.cancel()

    async def create_discord_thread_log(self):
        await self.bot.db.execute("""
        CREATE TABLE IF NOT EXISTS discord_threads(
            thread_id BIGINT NOT NULL,
            guild_id BIGINT NOT NULL,
            parent_id BIGINT NOT NULL,
            thread_list_msg_id BIGINT NOT NULL,
            thread_list_id BIGINT NOT NULL
        )
        """)

    async def create_thread_log(self):
        await self.bot.db.execute("""
        CREATE TABLE IF NOT EXISTS thread_channels(
            id SERIAL PRIMARY KEY,
            thread_creator BIGINT NOT NULL,
            invocation_channel_id BIGINT NOT NULL,
            invocation_message_id BIGINT NOT NULL,
            thread_channel_id BIGINT NOT NULL,
            copy_message_id BIGINT NOT NULL,
            reset_count INT NOT NULL DEFAULT 0,
            last_counter_increase TIMESTAMP,
            thread_title TEXT NOT NULL
        )
        """)
        await self.bot.db.execute("""
            ALTER TABLE thread_channels ADD COLUMN IF NOT EXISTS
            thread_creator BIGINT NOT NULL
        """)

    @commands.group(invoke_without_command=True)
    async def thread(self, ctx, *, topic):
        """
        create a new "thread" channel to discuss something with other people
        """

        open_threads = await self.bot.db.fetch("SELECT thread_channel_id, invocation_message_id, invocation_channel_id FROM thread_channels")
        if ctx.channel.id in [ot.get("thread_channel_id") for ot in open_threads]:
            return await ctx.send("you can't open another thread from within a thread") 
        category = ctx.guild.get_channel(self.settings.get("category_channel"))
        if not category:
            return await ctx.send(f"No category for channel creation set please use `{ctx.prefix}thread category` to set it")
        disc_channel = await category.create_text_channel(name=topic, topic=self.topic)
        thread_list_channel = self.bot.get_channel(self.settings.get("thread_list_channel"))
        await disc_channel.set_permissions(ctx.author, read_messages=True)
        embed = discord.Embed(title=f"Thread: {topic} \N{OPEN LOCK}", 
                description=f"To join the channel {disc_channel.mention} react with {self.settings.get('join_reaction')}\nremove reaction to leave", 
                colour=discord.Colour(green))
        thread_start = await ctx.send(embed=embed)
        thread_list_copy = await thread_list_channel.send(embed=embed)
        await disc_channel.send(textwrap.dedent(self.thread_rule.format(topic)))
        await thread_start.add_reaction(self.settings.get('join_reaction'))
        await thread_list_copy.add_reaction(self.settings.get('join_reaction'))
        await self.bot.db.execute("""
            INSERT INTO thread_channels (invocation_channel_id, invocation_message_id, thread_channel_id, copy_message_id, thread_title, thread_creator) VALUES ($1, $2, $3, $4, $5, $6)
        """, ctx.channel.id, thread_start.id, disc_channel.id, thread_list_copy.id, topic, ctx.author.id)


    @is_owner_or_moderator()
    @thread.command(name="category")
    async def thread_category(self, ctx, category: discord.CategoryChannel):
        """
        Set the category under which the thread/discussion channels should be created
        """
        with self.settings_path.open("w") as s:
            self.settings["category_channel"] = category.id
            json.dump(self.settings, s)
        await ctx.send(f"channel set to category: {category.name}")

    @is_owner_or_moderator()
    @thread.command(name="list")
    async def thread_set_list(self, ctx, channel: discord.TextChannel):
        """
        Set the channel which will host the thread list
        """
        with self.settings_path.open("w") as s:
            self.settings["thread_list_channel"] = channel.id
            json.dump(self.settings, s)
        await ctx.send(f"set thread list channel to: {channel.mention}")

    
    @is_owner_or_moderator()
    @thread.command(name="livetime", aliases=["lt"])
    async def thread_livetime(self, ctx, livetime: int=None):
        """
        Set how long the livetime (in hours) of the channel should be (meaning how long is it allowed to be inactive before getting deleted)
        """
        if not livetime:
            return await ctx.send(f"the current livetime is {self.settings.get('livetime')} hour(s)")
        if livetime <= 0:
            return await ctx.send("please only provided positive numbers bigger than 0")
        with self.settings_path.open("w") as s:
            self.settings["livetime"] = livetime
            json.dump(self.settings, s)
        await ctx.send(f"live time of the thread channels is now: {livetime} hours")

    @commands.guild_only()
    @thread.command(name="close", aliases=["delete"])
    async def thread_close(self, ctx, thread: discord.TextChannel):
        """
        Close a thread channel before its livetime is over
        """
        thread_info = await self.bot.db.fetchrow("""
        SELECT *
        FROM thread_channels 
        WHERE thread_channel_id = $1
        """, thread.id)
        if not thread_info:
            return await ctx.send(f"The channel {thread.mention} is not a thread channel")
        thread_channel = self.bot.get_channel(thread_info.get("thread_channel_id"))
        if thread_channel:
            permissions = thread_channel.permissions_for(ctx.author)
            thread_creator = ctx.guild.get_member(thread_info.get("thread_creator"))
            if not permissions.manage_channels and not thread_creator == ctx.author:
                return await ctx.send("Only thread creator or moderators are allowed to close a thread manually")
            thread_list_channel = self.bot.get_channel(self.settings.get("thread_list_channel"))
            copy_message = thread_list_channel.get_partial_message(thread_info.get("copy_message_id"))
            invocation_channel = self.bot.get_channel(thread_info.get("invocation_channel_id"))
            message = invocation_channel.get_partial_message(thread_info.get("invocation_message_id"))
            thread_id = await self.delete_thread(thread_channel, message, copy_message,thread_info, force=True)
            if thread_id: await self.db_delete_thread(thread_id)

    
    @tasks.loop(seconds=LOOP_TIME)
    async def check_activity(self):
        """
        iterate through open threads and check if they are inactive and can be deleted
        """
        self.logger.debug("starting check_activity...")
        await asyncio.wait_for(self.create_thread_table, timeout=None)
        open_threads = await self.bot.db.fetch("SELECT thread_channel_id, invocation_message_id, invocation_channel_id, copy_message_id, thread_title, reset_count, last_counter_increase FROM thread_channels")
        for thread in open_threads:
            thread_channel = self.bot.get_channel(thread.get("thread_channel_id"))
            if not thread_channel:
                return await self.db_delete_thread(thread.get("thread_channel_id"))
            last_message = next(iter(await thread_channel.history(limit=1).flatten()), None)
            schedule_delete = False
            current_livetime = round(2 * self.settings.get("livetime") * (0.75 ** thread.get("reset_count")))/2
            if thread.get("last_counter_increase"):
                increase_counter_at = thread.get("last_counter_increase") + (timedelta(hours=current_livetime))
            else:
                increase_counter_at = thread_channel.created_at + (timedelta(hours=current_livetime))
            if last_message:
                time_diff = datetime.utcnow() - last_message.created_at
                delete_at = last_message.created_at + timedelta(hours=current_livetime)
            else:
                time_diff = datetime.utcnow() - thread_channel.created_at
                delete_at = thread_channel.created_at + timedelta(hours=current_livetime)
            
            next_loop = self.check_activity.next_iteration.replace(tzinfo=None)
            if delete_at <= next_loop:
                schedule_delete = 'True'
            if increase_counter_at <= next_loop:
                counter_task = self.bot.loop.create_task(self.increase_counter(thread, increase_counter_at))
                counter_task.add_done_callback(self.set_counter_after_task)
                self.scheduled_tasks.append(counter_task)

                
            thread_list_channel = self.bot.get_channel(self.settings.get("thread_list_channel"))
            copy_message = thread_list_channel.get_partial_message(thread.get("copy_message_id"))
            invocation_channel = self.bot.get_channel(thread.get("invocation_channel_id"))
            message = invocation_channel.get_partial_message(thread.get("invocation_message_id"))

            if schedule_delete:
                deletion_task = self.bot.loop.create_task(self.delete_thread(thread_channel, message, copy_message, thread, delete_at))
                deletion_task.add_done_callback(self.thread_delete_error)
                self.scheduled_tasks.append(deletion_task)
            full_message = await copy_message.fetch()
            embed = full_message.embeds[0]
            hours, remainder = divmod(int(time_diff.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            livetime = self.settings.get("livetime") 
            if hours >= round(livetime *  (2/3)):
                embed.colour = discord.Colour(0xd89849)
            else:
                embed.colour = discord.Colour(green)
            embed.set_footer(text=f"Channel deletion at (if inactive for another {current_livetime} hour(s))")
            embed.timestamp = delete_at
            await full_message.edit(embed=embed)

    @check_activity.error
    async def check_activity_error(self, error):
        self.logger.error("unhandled error in check_activity loop:\n%s", error, exc_info=True)

    def set_counter_after_task(self, task: asyncio.Task):
        if task.cancelled():
            return self.logger.debug("task was cancelled : %s", task.get_name())
        if task.exception():
            self.logger.error("error when trying to increase counter:\n%s", task.exception(), exc_info=True)
    def thread_delete_error(self, task: asyncio.Task):
        if task.cancelled():
            return self.logger.debug("task was cancelled : %s", task.get_name())
        if task.exception():
            self.logger.error("error when trying to delete thread:\n%s", task.exception(), exc_info=True)
        else:
            self.logger.debug("result: %s", task.result())
            self.bot.loop.create_task(self.db_delete_thread(task.result()))
        
    async def increase_counter(self, thread_entry, increase_at):
        self.logger.debug("increase of counter for %s at %s", thread_entry.get("thread_title"), increase_at)
        await discord.utils.sleep_until(increase_at)
        await self.bot.db.execute("""
        UPDATE thread_channels SET reset_count = $1, last_counter_increase = $2 WHERE thread_channel_id = $3
        """, thread_entry.get("reset_count")+1, datetime.utcnow(),thread_entry.get("thread_channel_id") )

    async def db_delete_thread(self, thread_id):
        if thread_id:
            try:
                await self.bot.db.execute(""" DELETE FROM thread_channels WHERE thread_channel_id = $1""", thread_id)
            except Exception as e:
                self.logger.error("Error when trying to delete thread from database:\n%s", e, exc_info=True)
        else:
            self.logger.debug("No deletion needed channel was active")

    async def delete_thread(self, thread_channel, thread_message, copy_message, thread, delete_at=datetime.utcnow(), force=False):
        self.logger.debug("deletion of channel #%s at %s", thread_channel.name, delete_at)
        await discord.utils.sleep_until(delete_at)
        last_message = next(iter(await thread_channel.history(limit=1).flatten()), None)
        # one last activity check before deleting the channel
        current_livetime = round(2 * self.settings.get("livetime") * (0.75 ** thread.get("reset_count")))/2
        if not force and last_message and last_message.created_at + timedelta(hours=current_livetime) > delete_at:
            self.logger.debug("deletion aborted channel was active at %s, next deletion around: %s", last_message.created_at, last_message.created_at + timedelta(hours=current_livetime))
            return None
        chat_log = await self.generate_file(thread_channel)
        chat_log_message = await self.attachments_backlog.send(file=discord.File(chat_log, filename=f"{thread_channel.name}.txt"))
        embed = discord.Embed(title=f"Thread: {thread.get('thread_title')} \N{LOCK}", description="channel closed see the below text file for a chat log", colour=discord.Colour(red))
        embed.add_field(name="Chat log", value=f"[{thread_channel.name}.txt]({chat_log_message.attachments[0].url})")
        await thread_message.edit(embed=embed)
        await copy_message.edit(embed=embed)
        await thread_message.clear_reactions()
        await copy_message.clear_reactions()
        await thread_channel.delete()
        return thread_channel.id

    @commands.Cog.listener("on_raw_reaction_add")
    async def add_users_to_channel(self, payload):
        """
        reaction handler for adding people to a thread channel
        """
        if payload.user_id == self.bot.user.id or payload.emoji.name != self.settings.get('join_reaction') or not payload.guild_id:
            return
        if self.admin_cog and self.admin_cog.mute_role in payload.member.roles:
            return
        thread_channel = await self.bot.db.fetchval("""SELECT thread_channel_id FROM thread_channels WHERE invocation_message_id = $1 OR copy_message_id = $1""", payload.message_id)
        if thread_channel:
            thread_channel = self.bot.get_channel(thread_channel)
            await thread_channel.set_permissions(payload.member, read_messages=True)

    @commands.Cog.listener("on_raw_reaction_remove")
    async def remove_users_from_thread(self, payload):
        """
        reaction handler for adding people to a thread channel
        """
        if payload.user_id == self.bot.user.id or payload.emoji.name != self.settings.get('join_reaction') or not payload.guild_id:
            return
        thread_channel = await self.bot.db.fetchval("""SELECT thread_channel_id FROM thread_channels WHERE invocation_message_id = $1 OR copy_message_id = $1""", payload.message_id)
        if thread_channel:
            thread_channel = self.bot.get_channel(thread_channel)
            member = thread_channel.guild.get_member(payload.user_id)
            await thread_channel.set_permissions(member, overwrite=None)

def setup(bot):
    bot.add_cog(Thread(bot))
