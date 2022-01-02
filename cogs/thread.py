import discord
from discord.ext import commands, tasks
from .utils.checks import is_owner_or_moderator
from logging import getLogger
from typing import List, Optional
import textwrap
import asyncio

thread_duration_regex = r"\d+\s?"
class ThreadConversionException(commands.BadArgument):
    pass

class ThreadFetch(commands.ThreadConverter):

    async def convert(self, ctx: commands.Context, argument: str) -> discord.Thread:
        try:
            return await super().convert(ctx, argument)
        except:
            try:
                if not ctx.guild:
                    raise ThreadConversionException("Can't fetch for threads in a DM")
                thread_id = int(argument)
                thread = await ctx.guild.fetch_channel(thread_id)
                if not isinstance(thread, discord.Thread):
                    raise ThreadConversionException("Could not fetch thread")
            except ValueError:
                raise ThreadConversionException("could not fetch thread")

class ThreadSelect(discord.ui.Select):
    def __init__(self, threads: List[discord.Thread], guild: discord.Guild):
        self.guild = guild
        super().__init__(placeholder="Select Thread to get invited to", options=[discord.SelectOption(label=textwrap.shorten(t.name, 100), value=str(t.id)) for t in threads])

    async def callback(self, interaction: discord.Interaction):
        selection = self.values.pop(0)
        thread = self.guild.get_thread(int(selection)) or await self.guild.fetch_channel(int(selection))
        if not thread:
            await interaction.response.send_message("Could not fetch thread.")
        else:
            embed = discord.Embed(description="Click the Join Button to join the thread", title=thread.name)
            await interaction.response.send_message(embed=embed, view=ThreadJoinView(thread))
            if thread.archived and not thread.locked:
                await thread.edit(archived=False, locked=False)
            if interaction.user:
                await thread.add_user(interaction.user)

class ThreadSelectView(discord.ui.View):
     
    def __init__(self, threads: List[discord.Thread], guild: discord.Guild):
        super().__init__(timeout=180)
        self.add_item(ThreadSelect(threads,guild))

class ThreadJoinView(discord.ui.View):

    def __init__(self, thread: discord.Thread):
        self.thread = thread
        super().__init__(timeout=None)

    @discord.ui.button(label="Join", style=discord.ButtonStyle.primary)
    async def join_thread(self, button : discord.ui.Button, interaction: discord.Interaction):
        if interaction.user:
            if not self.thread.archived:
                self.thread = await self.thread.guild.fetch_channel(self.thread.id)
            if self.thread.archived:
                await self.thread.edit(archived=False, locked=False)
            await self.thread.add_user(interaction.user)

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
        self.db_task = self.bot.loop.create_task(self.init_database())
    
    async def cog_before_invoke(self, ctx: commands.Context):
        await asyncio.wait_for(self.db_task, timeout=None)

    async def init_database(self):
        await self.bot.db.execute('''
        CREATE TABLE IF NOT EXISTS threads(
            guild_id BIGINT NOT NULL,
            thread_id BIGINT NOT NULL,
            owner_id BIGINT NOT NULL,
            private BOOLEAN NOT NULL
        )
        ''')

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def thread(self, ctx: commands.Context, *, topic):
        """
        create a new private thread with open invite 
        """
        thread_type = discord.ChannelType.public_thread
        if ctx.guild.premium_tier >= 2:
            thread_type = discord.ChannelType.private_thread

        thread = await ctx.channel.create_thread(name=topic,type=thread_type)
        if thread.is_private():
            view = ThreadJoinView(thread)
            embed = discord.Embed(title=topic, description="Click the join button to join the private thread", colour=discord.Colour.blurple())
            await self.bot.db.execute('''
            INSERT INTO threads (guild_id, thread_id, owner_id, private) VALUES ($1,$2,$3,$4)
            ''', ctx.guild.id, thread.id, ctx.author.id, thread.is_private())
            await ctx.send(embed=embed, view=view)

    @thread.command(name="invite")
    @commands.guild_only()
    async def thread_post_invite(self, ctx: commands.Context, thread: Optional[ThreadFetch]):
        """
        post a new invite to an existing thread
        if no thread specified then you will get a dropdown for joining
        """
        if thread:
            view = ThreadJoinView(thread)
            embed = discord.Embed(title=thread.name, description="Click the join button to join the private thread", colour=discord.Colour.blurple())
            await ctx.send(embed=embed, view=view)

        else:
            thread_entities = await self.bot.db.fetch("""
                SELECT * FROM threads WHERE guild_id = $1 AND PRIVATE
            """, ctx.guild.id)
            threads = []
            for entity in thread_entities:
                t = ctx.guild.get_thread(entity.get('thread_id')) or await ctx.guild.fetch_channel(entity.get('thread_id'))
                threads.append(t)
            if not threads:
                return await ctx.send("No threads with invites in this channel")
            view = ThreadSelectView(threads, ctx.guild)
            embed = discord.Embed(title="Thread Selection", description="Select a thread you want to join")
            message = await ctx.send(embed=embed, view=view)
            await view.wait()
            await message.delete()

    @commands.guild_only()
    @thread.group(name="close", invoke_without_command=True)
    async def thread_close(self, ctx: commands.Context, thread: Optional[ThreadFetch]):
        """
        Close a thread channel before its livetime is over
        """
        if not thread and isinstance(ctx.channel, discord.Thread):
            thread = ctx.channel
        await thread.edit(archived=True, locked=False)
        if ctx.channel != thread:
            await ctx.message.add_reaction("\N{OK HAND SIGN}")

    @commands.guild_only()
    @is_owner_or_moderator()
    @thread_close.command(name="lock")
    async def thread_close_lock(self, ctx: commands.Context, thread: Optional[ThreadFetch]):
        """
        Close and lock a thread channel before its livetime is over
        """
        if not thread and isinstance(ctx.channel, discord.Thread):
            thread = ctx.channel
        await thread.edit(archived=True, locked=True)
        await self.bot.db.execute("""
            DELETE FROM threads WHERE guild_id = $1 AND thread_id = $2
        """, ctx.guild.id, thread.id)
        if ctx.channel != thread:
            await ctx.message.add_reaction("\N{OK HAND SIGN}")

def setup(bot):
    bot.add_cog(Thread(bot))
