from discord.ext import commands
import discord
from discord.utils import find
from .utils import checks
from aiohttp import ClientSession
import typing
import textwrap
from os import path
import json
import io
import asyncio

class JoinButton(discord.ui.Button):
    def __init__(self, thread):
        self.thread = thread
        super().__init__(label="Join", style=discord.ButtonStyle.blurple, custom_id=f"join_view:{self.thread.id}")

    async def callback(self, interaction: discord.Interaction):
        if self.thread.archived or self.thread.locked:
            await self.thread.edit(archived=False, locked=False)
            await self.thread.add_user(user=interaction.user)
            await self.thread.edit(archived=True, locked=False)
        else:
            await self.thread.add_user(user=interaction.user)


class JoinView(discord.ui.View):
    def __init__(self, thread: discord.Thread):
        super().__init__(timeout=None)
        self.thread = thread
        self.add_item(JoinButton(thread))


class GroupWatch(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.start_message = None
        self.session = ClientSession()
        self.title = None
        self.end_message = None
        groupwatch_settings = "config/groupwatch.json"
        self.muted_channel = None
        self.initialize_table = self.bot.loop.create_task(self.groupwatch_threads_table())
        self.view_initializiation = self.bot.loop.create_task(self.initialize_views())

    async def groupwatch_threads_table(self):
        await self.bot.db.execute("""
        CREATE TABLE IF NOT EXISTS groupwatches(
            thread_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            guild_id BIGINT NOT NULL
        )
        """)
    async def initialize_views(self):
        await asyncio.wait_for(self.initialize_table, timeout=None)
        entries = await self.bot.db.fetch("""
        SELECT * FROM groupwatches
        """)
        for entry in entries:
            guild = self.bot.get_guild(entry.get("guild_id"))
            channel = guild.get_channel(entry.get("channel_id"))
            thread = channel.get_thread(entry.get("thread_id"))
            if not thread:
                archived_threads = channel.archived_threads(limit=100)
                thread = await archived_threads.find(lambda t: t.id == entry.get("thread_id"))
            if thread:
                self.bot.add_view(JoinView(thread), message_id=entry.get("message_id"))
        print(self.bot.persistent_views)
        self.bot.groupwatch_views_added = True

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    @commands.group(name="groupwatch", aliases=["gw"], invoke_without_command=True)
    @checks.is_owner_or_moderator()
    async def groupwatch(self, ctx):
        """
        groupwatch commands mostly for deleting all the messages
        """
        await ctx.send_help(self.groupwatch)

    @groupwatch.command(name="start")
    @checks.is_owner_or_moderator()
    async def gw_start(self, ctx, start_message: typing.Optional[discord.Message], mute: typing.Optional[str], *, title: typing.Optional[str]=""):
        """
        set the start point of the groupwatch messages after this one will be deleted after groupwatch is over
        if mute is written before the title then the speak permission of the channel is set to False
        """
        if mute and mute.lower() in ("mute", "m"):
            if not ctx.author.voice:
                await ctx.send("Could not change permissions because you are not in a voice channel")
            else:
                vc = ctx.author.voice.channel
                overwrite_default = vc.overwrites_for(ctx.guild.default_role)
                overwrite_default.speak = False
                await vc.set_permissions(ctx.guild.default_role, overwrite=overwrite_default)
                self.muted_channel = vc
        else:
            if mute is None:
                mute = "groupwatch"
            title = f"{mute} {title}"
        self.groupwatch_channel = ctx.channel
        self.groupwatch_role = find(lambda r: r.name == "Groupwatch", ctx.guild.roles)
        if title:
            self.title = "".join([c for c in title if c.isalpha() or c.isdigit() or c ==' ']).rstrip()
        else: 
            self.title = None
        if not self.groupwatch_role:
            await ctx.send("Could not find Groupwatch role. "
                           "Therefore now permissions changed")
        else:
            overwrites_gw = ctx.channel.overwrites_for(self.groupwatch_role)
            overwrites_gw.read_messages = True
            await ctx.channel.set_permissions(self.groupwatch_role,
                                          overwrite=overwrites_gw)
        if ctx.guild.premium_tier >= 2:
            thread_type = discord.ChannelType.private_thread
        else:
            thread_type = discord.ChannelType.public_thread
        embed = discord.Embed(title=self.title, description="Groupwatch thread created join via button", colour=self.groupwatch_role.colour)
        self.groupwatch_thread = await ctx.channel.start_thread(name=self.title, type=thread_type, auto_archive_duration=60)
        self.groupwatch_view = JoinView(self.groupwatch_thread)
        self.start_message = await ctx.send(embed=embed, view=self.groupwatch_view)
        await self.bot.db.execute("""
        INSERT INTO groupwatches(thread_id, message_id, channel_id, guild_id) 
        VALUES ($1, $2, $3, $4)
        """, self.groupwatch_thread.id, self.start_message.id, self.start_message.channel.id, self.start_message.guild.id)


    @groupwatch.command(name="end")
    @checks.is_owner_or_moderator()
    async def gw_end(self, ctx):
        """
        set the endpoint of the groupwatch and upload a text file of the chat log
        """ 
        if not self.start_message:
            return await ctx.send("No start message set, use `.gw start`")
        self.groupwatch_channel = ctx.channel
        self.groupwatch_role = find(lambda r: r.name == "Groupwatch", ctx.guild.roles)
        if not self.groupwatch_role:
            await ctx.send("Could not find Groupwatch role. "
                           "Therefore now permissions changed")
        else:
            overwrites_gw = ctx.channel.overwrites_for(self.groupwatch_role)
            overwrites_gw.read_messages = False
            await ctx.channel.set_permissions(self.groupwatch_role,
                                          overwrite=overwrites_gw)
        await self.groupwatch_thread.edit(archived=True)
        await self.start_message.edit(content="Groupwatch ended", view=self.groupwatch_view)
        self.start_message = None
        self.groupwatch_view = None
        self.groupwatch_thread = None
        

    async def generate_chatlog(self, ctx):
            f = io.StringIO()
            await self.generate_file(ctx, f)
            f.seek(0)
            return f
    async def get_attachment_links(self, ctx, message):
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


    async def generate_file(self, ctx, f):
        async for message in ctx.channel.history(after=self.start_message, before=self.end_message, limit=None):
            attachments = await self.get_attachment_links(ctx, message)
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
        await ctx.channel.purge(after=self.start_message, before=self.end_message, limit=None)
        f.seek(0)
        chat_msg = f.read()
        return chat_msg

    async def upload_to_hastebin(self, ctx, chat_message):
        async with self.session.post(url=f"https://hastebin.com/documents", data=chat_message) as resp:
            filename = self.title+".txt" if self.title else None
            if resp.status == 200:
                data = await resp.json()
                await ctx.send(f"https://hastebin.com/{data.get('key')}", file=discord.File("data/groupwatch_chatlog.txt", filename=filename))
            else:
                await ctx.send(content=f"Could not create file on hastebin\nreason: `{resp.reason}`", file=discord.File("data/groupwatch_chatlog.txt", filename=filename))
def setup(bot):
    bot.add_cog(GroupWatch(bot))
