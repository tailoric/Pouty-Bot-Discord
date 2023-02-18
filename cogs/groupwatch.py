import asyncio
import textwrap
import typing
import itertools
from thefuzz import process
from thefuzz import fuzz
from typing import Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .utils import checks
from itertools import filterfalse

class JoinButton(discord.ui.Button):
    def __init__(self, thread):
        self.thread = thread
        super().__init__(label="Join", style=discord.ButtonStyle.blurple, custom_id=f"join_view:{self.thread.id}")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.thread.edit(archived=False, locked=False)
        await self.thread.add_user(interaction.user)
        await interaction.followup.send(f"Added you to the thread {self.thread.mention}", ephemeral=True)


class JoinView(discord.ui.View):

    def __init__(self, thread: discord.Thread):
        super().__init__(timeout=None)
        self.thread = thread
        self.add_item(JoinButton(thread))
        self.cog = None


class GroupwatchSelect(discord.ui.Select):

    def __init__(self, threads: List[discord.Thread], is_open: bool):
        options = [discord.SelectOption(label=textwrap.shorten(thread.name, 25), value=str(thread.id)) for thread in threads]
        self.threads = {t.id : t for t in threads}
        self.is_open = is_open
        if is_open:
            placeholder = "Choose which groupwatch to start"
        else:
            placeholder = "Choose which groupwatch to end"
        super().__init__(placeholder=placeholder, options=options, max_values=1)

    async def callback(self, interaction : discord.Interaction):
        thread = self.threads.get(int(self.values.pop()))
        if not thread:
            return await interaction.response.send_message("Something went wrong could not find thread")
        if self.is_open:
            embed = discord.Embed(title=thread.name, description="Groupwatch thread created join via button", colour=thread.guild.me.colour)
            view = JoinView(thread)
            view.cog = self.view.cog
            await interaction.response.send_message(embed=embed, view=view)
            await thread.edit(archived=False)
            await thread.send("@everyone")
            await interaction.message.edit(view=self.view)
        else:
            await thread.edit(archived=True)
            if self.view:
                self.disabled = True
                await interaction.response.edit_message(view=self.view)
                self.view.stop()


class ArchiveSelect(discord.ui.Select):
    def __init__(self, threads: List[discord.Thread], ctx: commands.Context):
        options = [discord.SelectOption(label=textwrap.shorten(thread.name, 25), value=str(thread.id)) for thread in threads]
        self.threads = {t.id : t for t in threads}
        self.ctx = ctx
        super().__init__(placeholder="choose which groupwatch to end permanently", options=options)


    async def callback(self, interaction: discord.Interaction):
        if self.view:
            chosen = int(self.values.pop())
            async with self.ctx.bot.db.acquire() as con, con.transaction():
                deleted = await con.fetchrow("""
                DELETE FROM groupwatches WHERE thread_id = $1
                RETURNING guild_id
                """, chosen)
                await con.execute("""SELECT pg_notify('groupwatch', $1)""", str(deleted.get("guild_id")))
            thread = await self.ctx.bot.fetch_channel(chosen)
            new_options = list(filterfalse(lambda o: o.value == str(chosen), self.options))
            if not thread.archived:
                await thread.edit(archived=True)
            if new_options:
                self.options = new_options
            else:
                self.disabled = True
            await interaction.response.edit_message(view=self.view)


class GroupwatchesSelectView(discord.ui.View):

    def __init__(self, threads: List[discord.Thread], author: discord.Member, cog : 'GroupWatch', is_open: bool,*args, **kwargs):
        super().__init__(timeout=None, *args, **kwargs)
        self.author = author
        self.cog = cog
        self.add_item(GroupwatchSelect(threads, is_open=is_open))


    async def interaction_check(self, interaction : discord.Interaction):
        if interaction.user and interaction.user.id == self.author.id:
            return True
        else:
            return False

class GroupWatchJoinSelectView(discord.ui.View):

    def __init__(self, threads: List[discord.Thread]):
        super().__init__(timeout=None)
        self.add_item(GroupwatchJoinSelect(threads))

class GroupwatchJoinSelect(discord.ui.Select):

    def __init__(self, threads: List[discord.Thread]):
        options = list(itertools.islice([discord.SelectOption(label=textwrap.shorten(thread.name, 25), value=str(thread.id)) for thread in threads], 25))
        self.threads = {t.id : t for t in threads}
        placeholder = "Choose which groupwatch thread to join"
        super().__init__(placeholder=placeholder, options=options, max_values=1)

    async def callback(self, interaction : discord.Interaction):
        thread = self.threads.get(int(self.values.pop()))
        if not thread:
            return await interaction.response.send_message("Something went wrong could not find thread")
        if interaction.user:
            if thread.archived:
                await thread.edit(archived=False)
            await thread.add_user(interaction.user)
            await interaction.response.send_message(f"You have been added to {thread.mention}", ephemeral=True)


class ArchiveSelectView(discord.ui.View):
    def __init__(self, threads: List[discord.Thread], ctx: commands.Context):
        super().__init__()
        self.chosen = None
        self.author = ctx.author
        self.ctx = ctx
        self.add_item(ArchiveSelect(threads, ctx))

    async def interaction_check(self, interaction : discord.Interaction):
        if interaction.user and interaction.user.id == self.author.id:
            return True
        else:
            return False

class GroupwatchThreadNotFound(app_commands.AppCommandError):
    pass

class GroupwatchThreadInvalidOption(app_commands.AppCommandError):
    pass 
class GroupWatchAuthorThreadTransformer(app_commands.Transformer):

    async def transform(self, interaction: discord.Interaction, value: str) -> discord.Thread:
        if interaction.guild:
            try:
                thread = await interaction.guild.fetch_channel(int(value))
                if isinstance(thread, discord.Thread):
                    return thread
            except discord.NotFound:
                raise GroupwatchThreadNotFound(f"Thread with id {value} not found")
            except ValueError:
                raise GroupwatchThreadInvalidOption(f"Thread with name or id `{value}` does not exist. Use `/groupwatch create` to create it")
                

        raise GroupwatchThreadNotFound(f"Thread with id {value} not found")

    async def autocomplete(self, interaction: discord.Interaction, current: str)->List[app_commands.Choice[str]]:
        if not interaction.guild:
            return []
        await interaction.response.defer()
        if interaction.guild.id not in interaction.client.groupwatches:
            interaction.client.groupwatches[interaction.guild.id] = await interaction.client.db.fetch("""
            SELECT thread_id, title, creator_id from groupwatches WHERE guild_id = $1
        """, interaction.guild.id)
        guild_threads = filter(lambda g: g.get("creator_id") == interaction.user.id, interaction.client.groupwatches[interaction.guild.id])
        if len(current) == 0:
            choices = [app_commands.Choice(name=g.get("title"), value=str(g.get("thread_id"))) for g in guild_threads]
        else:
            choices = [app_commands.Choice(name=g.get("title"), value=str(g.get("thread_id"))) for g in guild_threads if fuzz.partial_ratio(current.lower(), g.get("title").lower()) > 70]
        return choices[:25]

class GroupWatchGuildThreadTransformer(app_commands.Transformer):

    async def transform(self, interaction: discord.Interaction, value: str) -> discord.Thread:
        if interaction.guild:
            try:
                thread = await interaction.guild.fetch_channel(int(value))
                if isinstance(thread, discord.Thread):
                    return thread
            except discord.NotFound:
                raise GroupwatchThreadNotFound(f"Thread with id {value} not found")

        raise GroupwatchThreadNotFound(f"Thread with id {value} not found")

    async def autocomplete(self, interaction: discord.Interaction, current: str)->List[app_commands.Choice[str]]:
        if not interaction.guild:
            return []
        await interaction.response.defer()
        if interaction.guild.id not in interaction.client.groupwatches:
            interaction.client.groupwatches[interaction.guild.id] = await interaction.client.db.fetch("""
            SELECT thread_id, title, creator_id from groupwatches WHERE guild_id = $1
        """, interaction.guild.id)
        guild_threads = interaction.client.groupwatches[interaction.guild.id]
        if len(current) == 0:
            choices = [app_commands.Choice(name=g.get("title"), value=str(g.get("thread_id"))) for g in guild_threads]
        else:
            choices = [app_commands.Choice(name=g.get("title"), value=str(g.get("thread_id"))) for g in guild_threads if fuzz.partial_ratio(current.lower(), g.get("title").lower()) > 70]
        return choices[:25]

class GroupWatch(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        if not hasattr(self.bot, "groupwatches"):
            self.bot.groupwatches = {}
        self.start_message = None

    async def cog_load(self):
        self.initialize_table = self.bot.loop.create_task(self.groupwatch_threads_table())
        async def listener_callback(connection, pid, channel, payload):
            self.bot.groupwatches[int(payload)] = await self.bot.db.fetch("""
            SELECT thread_id, title, creator_id from groupwatches WHERE guild_id = $1
            """, int(payload))
        self.con = await self.bot.db.acquire()
        await self.con.add_listener('groupwatch', listener_callback)
        for guild in self.bot.guilds:
            self.bot.groupwatches[guild.id] = await self.bot.db.fetch("""
            SELECT thread_id, title, creator_id from groupwatches WHERE guild_id = $1
            """, guild.id)
             
    async def cog_unload(self):
        await self.con.close()
    async def groupwatch_threads_table(self):
        await self.bot.db.execute("""
        CREATE TABLE IF NOT EXISTS groupwatches(
            thread_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            creator_id BIGINT NOT NULL,
            title TEXT NOT NULL,
            guild_id BIGINT NOT NULL
        )
        """)




    @commands.hybrid_group(name="groupwatch", aliases=["gw"], invoke_without_command=True)
    async def groupwatch(self, ctx):
        """
        groupwatch commands

        for creating long running threads that can be opened and closed whenever a groupwatch is happening
        """
        await ctx.send_help(self.groupwatch)

    
    @groupwatch.command(name="join")
    @commands.guild_only()
    async def gw_join(self, ctx: commands.Context, thread: Optional[app_commands.Transform[discord.Thread, GroupWatchGuildThreadTransformer]]):
        """
        Join any currently running groupwatch

        Parameters
        ---------
        thread: str
            The groupwatch you want to join
        """
        if thread:
            await ctx.defer(ephemeral=True)
            was_archived = thread.archived
            if was_archived:
                await thread.edit(archived=False)
            await thread.add_user(ctx.author)
            if ctx.interaction:
                await ctx.send(f"You have been added to {thread.mention}", ephemeral=True)
            return
        groupwatches = await self.bot.db.fetch("""
        SELECT thread_id, channel_id from groupwatches WHERE guild_id = $1
        """, ctx.guild.id)
        groupwatch_threads : List[discord.Thread] = []
        if not groupwatches:
            return await ctx.send("no open groupwatches running")
        for groupwatch in groupwatches:
            thread = await self.bot.fetch_channel(groupwatch.get("thread_id"))
            if thread:
                groupwatch_threads.append(thread)

        await ctx.send("Please choose which groupwatch to join", view=GroupWatchJoinSelectView(groupwatch_threads))

    @groupwatch.command(name="leave")
    @commands.guild_only()
    async def gw_leave(self, ctx: commands.Context, thread: Optional[discord.Thread]):
        """
        leave a groupwatch thread
        
        Parameters
        ----------
        thread: discord.Thread
           The thread you want to leave
        """
        if isinstance(ctx.channel, discord.Thread):
            groupwatches = await self.bot.db.fetch("""
            SELECT thread_id from groupwatches WHERE guild_id = $1
            """, ctx.guild.id)
            
            if ctx.channel.id in (g.get('thread_id') for g in groupwatches):
                await ctx.channel.remove_user(ctx.author)
                if ctx.interaction:
                    await ctx.interaction.response.send_message(f"you got removed from thread {ctx.channel.mention}", ephemeral=True)
            else:
                await ctx.send("not a groupwatch channel")
        elif thread:
            await thread.remove_user(ctx.author)
            if ctx.interaction:
                await ctx.interaction.response.send_message(f"you got removed from thread {thread.mention}", ephemeral=True)
        else:
            await ctx.send("Please provide a thread as argument or use it inside a thread.")


    @groupwatch.command(name="create")
    @commands.guild_only()
    async def gw_create(self, ctx, *, title):
        """
        Create a groupwatch thread and add it to the database

        Parameters
        ----------
        title: str
           the title of the thread
        """
        if ctx.guild.premium_tier >= 2:
            thread_type = discord.ChannelType.private_thread
        else:
            thread_type = discord.ChannelType.public_thread
        embed = discord.Embed(title=title, description="Groupwatch thread created join via button", colour=ctx.guild.me.colour)
        groupwatch_thread = await ctx.channel.create_thread(name=title, type=thread_type, auto_archive_duration=60)
        groupwatch_view = JoinView(groupwatch_thread)
        groupwatch_view.cog = self
        start_message = await ctx.send(embed=embed, view=groupwatch_view)
        async with self.bot.db.acquire() as con, con.transaction():
            await self.bot.db.execute("""
            INSERT INTO groupwatches(thread_id, title, message_id, channel_id, guild_id, creator_id) 
            VALUES ($1, $2, $3, $4, $5, $6);
            """, groupwatch_thread.id, title, start_message.id, start_message.channel.id, start_message.guild.id, ctx.author.id)
            await self.bot.db.execute("""SELECT pg_notify('groupwatch', $1)""", str(start_message.guild.id))

    @groupwatch.command(name="start")
    @commands.guild_only()
    async def gw_start(self, ctx: commands.Context, thread: Optional[app_commands.Transform[discord.Thread,GroupWatchAuthorThreadTransformer]]):
        """
        start a groupwatch, will ping everyone inside the thread

        Parameters
        ----------
        thread: 
            The thread to open for the groupwatch
        """
        if thread:
            await ctx.defer(ephemeral=False)
            creator = await self.bot.db.fetchval("""
            SELECT creator_id FROM groupwatches WHERE thread_id = $1
            """, thread.id)            
            if not creator:
                await ctx.send(f"Groupwatch with id `{thread}` not found.", ephemeral=True)
            elif int(creator) == ctx.author.id:
                await thread.edit(archived=False)
                await thread.send("@everyone")
                groupwatch_view = JoinView(thread)
                await ctx.send(embed=discord.Embed(title=thread.name, description="Groupwatch thread created join via button", colour=thread.guild.me.colour), view=groupwatch_view)
            else:
                await ctx.send("You don't own this groupwatch")
                return
        else:
            groupwatches = await self.bot.db.fetch("""
            SELECT thread_id, channel_id from groupwatches WHERE guild_id = $1 AND creator_id = $2
            """, ctx.guild.id, ctx.author.id)
            groupwatch_threads : List[discord.Thread] = []
            if len(groupwatches) == 0:
                return await ctx.send("You have no groupwatches active, create one with `gw create`")
            for groupwatch in groupwatches:
                try:
                    thread = await self.bot.fetch_channel(groupwatch.get("thread_id"))
                    if thread:
                        groupwatch_threads.append(thread)
                except discord.NotFound:
                    async with self.bot.db.acquire() as con, con.transaction():
                        deleted = await con.fetchrow("""
                        DELETE FROM groupwatches WHERE thread_id = $1
                        RETURNING guild_id
                        """, groupwatch.get('thread_id'))
                        await con.execute("""SELECT pg_notify('groupwatch', $1)""", str(deleted.get("guild_id")))

            if(len(groupwatch_threads) == 0):
                return await ctx.send("There are no groupwatches active, create one with `gw create`")
            await ctx.send("Please choose which groupwatch to start", view=GroupwatchesSelectView(groupwatch_threads, ctx.author, self, is_open=True))

    @groupwatch.command(name="end")
    @commands.guild_only()
    async def gw_end(self, ctx: commands.Context, thread: Optional[app_commands.Transform[discord.Thread, GroupWatchAuthorThreadTransformer]]):
        """
        end the current groupwatch or select one groupwatch to end for this episode/view session

        Parameters
        ----------
        thread: 
            The thread to close
        """
        if thread:
            creator = await self.bot.db.fetchval("""
            SELECT creator_id FROM groupwatches WHERE thread_id = $1
            """, thread)
            if not creator:
                await ctx.send(f"Groupwatch with id `{thread}` not found.", ephemeral=True)
            elif int(creator) == ctx.author.id:
                await thread.edit(archived=True)
                if ctx.interaction:
                    await ctx.send(f"{thread.mention} closed", ephemeral=True)
            else:
                await ctx.send("You don't own this groupwatch", ephemeral=True)
            return
        user_threads = await self.bot.db.fetch("""
        SELECT thread_id FROM groupwatches WHERE guild_id = $1 AND creator_id = $2
        """,ctx.guild.id, ctx.author.id)
        if isinstance(ctx.channel, discord.Thread):
            if ctx.channel.id in [t.get('thread_id') for t in user_threads]:
                await ctx.channel.edit(archived=True)
            else:
                await ctx.send("Only owner of this thread can close")
        else:
            open_threads = [ctx.channel.get_thread(t.get('thread_id')) for t in user_threads if ctx.channel.get_thread(t.get('thread_id')) != None]
            if open_threads:
                await ctx.send("Please choose which groupwatch to end", view=GroupwatchesSelectView(open_threads, ctx.author, self, is_open=False))
            else:
                await ctx.send("None of your groupwatches are open")

    @groupwatch.command(name="complete", aliases=["over", "finish"])
    @commands.guild_only()
    async def gw_archive(self, ctx:commands.Context, thread: Optional[app_commands.Transform[discord.Thread, GroupWatchAuthorThreadTransformer]]):
        """
        Finish a groupwatch and remove it from the list of active groupwatches

        Parameters
        ----------
        thread:
            The groupwatch thread you want to archive
        """ 
        if thread:
            creator = await self.bot.db.fetchval("""
            SELECT creator_id FROM groupwatches WHERE thread_id = $1
            """, thread.id)
            if not creator:
                await ctx.send(f"Groupwatch with id `{thread}` not found.", ephemeral=True)
            elif int(creator) == ctx.author.id:
                await thread.edit(archived=True, locked=True)
                if ctx.interaction:
                    await ctx.send(f"{thread.mention} archived", ephemeral=True)
                async with ctx.bot.db.acquire() as con, con.transaction():
                    await con.execute("DELETE FROM groupwatches WHERE thread_id = $1", thread.id)
                    await con.execute("""SELECT pg_notify('groupwatch', $1)""", str(thread.guild.id))
            else:
                await ctx.send("You don't own this groupwatch")
            return
        async with ctx.typing():
            groupwatches = await self.bot.db.fetch("""
            SELECT thread_id, channel_id from groupwatches WHERE guild_id = $1 AND creator_id = $2
            """, ctx.guild.id, ctx.author.id)
            if len(groupwatches) == 0:
                return await ctx.send("No active groupwatches in the list, create one with `gw create`")
            threads = []
            for groupwatch in groupwatches:
                try:
                    threads.append(await self.bot.fetch_channel(groupwatch.get("thread_id")))
                except discord.NotFound:
                    continue
            archive = ArchiveSelectView(threads, ctx)
        await ctx.send("Choose a groupwatch to archive", view=archive)


async def setup(bot):
    await bot.add_cog(GroupWatch(bot))
