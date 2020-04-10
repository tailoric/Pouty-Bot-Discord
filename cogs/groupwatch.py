from discord.ext import commands
import discord
from .utils import checks
from aiohttp import ClientSession
import typing


class GroupWatch(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.start_message = None
        self.session = ClientSession()
        self.end_message = None

    @commands.group(name="groupwatch", aliases=["gw"], invoke_without_command=True) 
    @checks.is_owner_or_moderator()
    async def groupwatch(self, ctx):
        """
        groupwatch commands mostly for deleting all the messages
        """
        await ctx.send_help(self.groupwatch)

    @groupwatch.command(name="start")
    @checks.is_owner_or_moderator()
    async def gw_start(self, ctx, start_message: typing.Optional[discord.Message]):
        """
        set the start point of the groupwatch messages after this one will be deleted after groupwatch is over
        """
        if start_message:
            self.start_message = start_message
            await ctx.send("start messsage set.")
        else:
            self.start_message = await ctx.send("start message set.")

    @groupwatch.command(name="end")
    @checks.is_owner_or_moderator()
    async def gw_end(self, ctx, end_message: typing.Optional[discord.Message]):
        """
        set the endpoint of the groupwatch and upload a text file of the chat log
        """
        if end_message:
            self.end_message = end_message
        else:
            self.end_message = ctx.message
        with open("data/groupwatch_chatlog.txt", "w+", encoding="utf-8") as f:
            async for message in ctx.channel.history(after=self.start_message, before=self.end_message):
                attachments = f"\t[attachments:{', '.join([a.url for a in message.attachments])}]\n" if\
                        message.attachments else ""
                f.write(f"{message.created_at.strftime('%Y-%m-%d %H:%M:%S %Z')} "
                        f"@{message.author}: {message.clean_content}\n"
                        f"{attachments}")
            await ctx.channel.purge(after=self.start_message, before=self.end_message)
            f.seek(0)
            chat_msg = f.read()
            async with self.session.post(url=f"https://hastebin.com/documents", data=chat_msg) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    await ctx.send(f"https://hastebin.com/{data.get('key')}", file=discord.File("data/groupwatch_chatlog.txt"))
                else:
                    await ctx.send(content="something went wrong.", file=discord.File("data/groupwatch_chatlog.txt"))

def setup(bot):
    bot.add_cog(GroupWatch(bot))
