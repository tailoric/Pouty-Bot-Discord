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

class GroupWatch(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.start_message = None
        self.session = ClientSession()
        self.title = None
        self.end_message = None
        groupwatch_settings = "config/groupwatch.json"
        if not path.exists(groupwatch_settings):
            with open(groupwatch_settings, 'w') as f:
                settings = {"backlog_channel": None}
                json.dump(settings, f)
        with open(groupwatch_settings, 'r') as f:
            settings = json.load(f)
            self.attachments_backlog = self.bot.get_channel(settings.get("backlog_channel", None))
            

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
    async def gw_start(self, ctx, start_message: commands.Greedy[discord.Message], *, title: typing.Optional[str],):
        """
        set the start point of the groupwatch messages after this one will be deleted after groupwatch is over
        """
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
            await ctx.channel.set_permissions(self.groupwatch_role,
                                          read_messages=True)
        if start_message:
            self.start_message = start_message[0]
            await ctx.send(f"start message set. Title: {self.title}")
        else:
            self.start_message = await ctx.send("start message set.")

    @groupwatch.command(name="end")
    @checks.is_owner_or_moderator()
    async def gw_end(self, ctx, end_message: typing.Optional[discord.Message]):
        """
        set the endpoint of the groupwatch and upload a text file of the chat log
        """ 
        self.groupwatch_channel = ctx.channel
        self.groupwatch_role = find(lambda r: r.name == "Groupwatch", ctx.guild.roles)
        if not self.groupwatch_role:
            await ctx.send("Could not find Groupwatch role. "
                           "Therefore now permissions changed")
        else:
            await ctx.channel.set_permissions(self.groupwatch_role,
                                          read_messages=False)
        if end_message:
            self.end_message = end_message
        else:
            self.end_message = ctx.message
        async with ctx.typing():
            await self.generate_chatlog(ctx)

    async def generate_chatlog(self, ctx):
        with open("data/groupwatch_chatlog.txt", "w+", encoding="utf-8") as f:
            chat_message = await self.generate_file(ctx, f)
            await self.upload_to_hastebin(ctx, chat_message)

    async def get_attachment_links(self, ctx, message):
        attachment_string_format = "\t[attachments: {}]\n" 
        if not self.attachments_backlog:
            urls = [a.url for a in message.attachments]
            return attachment_string_format.format(','.join(urls)) if urls else ""
        attachment_list = []
        for attach in message.attachments:
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
