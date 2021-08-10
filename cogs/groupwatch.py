import asyncio
import textwrap
import typing
from typing import Dict, List, Optional

import discord
from discord.ext import commands

from .utils import checks

class JoinButton(discord.ui.Button):
    def __init__(self, thread):
        self.thread = thread
        super().__init__(label="Join", style=discord.ButtonStyle.blurple, custom_id=f"join_view:{self.thread.id}")

    async def callback(self, interaction: discord.Interaction):
        await self.thread.edit(archived=False, locked=False)
        await self.thread.add_user(user=interaction.user)
        if self.view and self.view.cog:
            self.view.cog.open_threads[self.thread.id] = self.thread


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
            if self.view:
                self.view.cog.open_threads[thread.id] = thread
        else:
            await thread.edit(archived=True)
            if self.view:
                self.view.cog.open_threads.pop(thread.id)
                self.disabled = True
                await interaction.response.edit_message(view=self.view)
                self.view.stop()


class ArchiveSelect(discord.ui.Select):
    def __init__(self, threads: List[discord.Thread]):
        options = [discord.SelectOption(label=textwrap.shorten(thread.name, 25), value=str(thread.id)) for thread in threads]
        self.threads = {t.id : t for t in threads}
        super().__init__(placeholder="choose which groupwatch to end permanently", options=options)


    async def callback(self, interaction: discord.Interaction):
        if self.view:
            self.view.chosen = int(self.values[0])
            self.disabled = True
            await interaction.response.edit_message(view=self.view)
            self.view.stop()


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
        options = [discord.SelectOption(label=textwrap.shorten(thread.name, 25), value=str(thread.id)) for thread in threads]
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
            if thread.archived:
                await thread.edit(archived=True)
                await interaction.response.send_message("You have been added to the thread but it is currently archived you will see it when the channel is opened again", ephemeral=True)

class ArchiveSelectView(discord.ui.View):
    def __init__(self, threads: List[discord.Thread], author: discord.Member):
        super().__init__()
        self.chosen = None
        self.author = author
        self.add_item(ArchiveSelect(threads))

    async def interaction_check(self, interaction : discord.Interaction):
        if interaction.user and interaction.user.id == self.author.id:
            return True
        else:
            return False

class GroupWatch(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.start_message = None
        self.initialize_table = self.bot.loop.create_task(self.groupwatch_threads_table())
        self.view_initializiation = self.bot.loop.create_task(self.initialize_views())
        self.open_threads : Dict[int, discord.Thread]= {}

    async def groupwatch_threads_table(self):
        await self.bot.db.execute("""
        CREATE TABLE IF NOT EXISTS groupwatches(
            thread_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            title TEXT NOT NULL,
            guild_id BIGINT NOT NULL
        )
        """)

    async def initialize_views(self):
        await asyncio.wait_for(self.initialize_table, timeout=None)
        entries = await self.bot.db.fetch("""
        SELECT * FROM groupwatches
        """)
        for entry in entries:
            guild : discord.Guild = self.bot.get_guild(entry.get("guild_id"))
            thread : Optional[discord.Thread] = guild.get_thread(entry.get("thread_id"))
            if thread and not thread.archived:
                self.open_threads[thread.id] = thread


    @commands.group(name="groupwatch", aliases=["gw"], invoke_without_command=True)
    async def groupwatch(self, ctx):
        """
        groupwatch commands, for creating long running threads that can be opened and closed whenever a groupwatch is happening
        """
        await ctx.send_help(self.groupwatch)

    
    @groupwatch.command(name="join")
    async def gw_join(self, ctx: commands.Context):
        """
        Join any currently running groupwatch
        """
        groupwatches = await self.bot.db.fetch("""
        SELECT thread_id, channel_id from groupwatches WHERE guild_id = $1
        """, ctx.guild.id)
        groupwatch_threads : List[discord.Thread] = []
        for groupwatch in groupwatches:
            thread = await self.bot.fetch_channel(groupwatch.get("thread_id"))
            if thread:
                groupwatch_threads.append(thread)

        await ctx.send("Please choose which groupwatch to join", view=GroupWatchJoinSelectView(groupwatch_threads))
    @groupwatch.command(name="create")
    @checks.is_owner_or_moderator()
    async def gw_create(self, ctx, *, title):
        """
        Create a groupwatch thread and add it to the database
        """
        if ctx.guild.premium_tier >= 2:
            thread_type = discord.ChannelType.private_thread
        else:
            thread_type = discord.ChannelType.public_thread
        embed = discord.Embed(title=title, description="Groupwatch thread created join via button", colour=ctx.guild.me.colour)
        groupwatch_thread = await ctx.channel.start_thread(name=title, type=thread_type, auto_archive_duration=60)
        groupwatch_view = JoinView(groupwatch_thread)
        groupwatch_view.cog = self
        start_message = await ctx.send(embed=embed, view=groupwatch_view)
        self.open_threads[groupwatch_thread.id] = groupwatch_thread
        await self.bot.db.execute("""
        INSERT INTO groupwatches(thread_id, title, message_id, channel_id, guild_id) 
        VALUES ($1, $2, $3, $4, $5)
        """, groupwatch_thread.id, title, start_message.id, start_message.channel.id, start_message.guild.id)


    @groupwatch.command(name="start")
    @checks.is_owner_or_moderator()
    async def gw_start(self, ctx: commands.Context):
        """
        start a groupwatch by selecting one of the currently active groupwatches from the dropdown
        """
        groupwatches = await self.bot.db.fetch("""
        SELECT thread_id, channel_id from groupwatches WHERE guild_id = $1
        """, ctx.guild.id)
        groupwatch_threads : List[discord.Thread] = []
        if len(groupwatches) == 0:
            return await ctx.send("There are now groupwatches active, create one with `gw create`")
        for groupwatch in groupwatches:
            thread = await self.bot.fetch_channel(groupwatch.get("thread_id"))
            if thread:
                groupwatch_threads.append(thread)

        await ctx.send("Please choose which groupwatch to start", view=GroupwatchesSelectView(groupwatch_threads, ctx.author, self, is_open=True))

    @groupwatch.command(name="end")
    @checks.is_owner_or_moderator()
    async def gw_end(self, ctx: commands.Context):
        """
        end the current groupwatch or select one groupwatch to end for this episode/view session
        """
        if len(self.open_threads) == 0:
            await ctx.send("No groupwatch running")
        elif len(self.open_threads) == 1:
            thread_id, thread =  self.open_threads.popitem()
            await thread.edit(archived=True)
        else:
            await ctx.send("Please choose which groupwatch to end", view=GroupwatchesSelectView(list(self.open_threads.values()), ctx.author, self, is_open=False))

    @groupwatch.command(name="complete", aliases=["over", "finish"])
    @checks.is_owner_or_moderator()
    async def gw_archive(self, ctx):
        """
        Finish a groupwatch and remove it from the list of active groupwatches
        """ 
        groupwatches = await self.bot.db.fetch("""
        SELECT thread_id, channel_id from groupwatches WHERE guild_id = $1
        """, ctx.guild.id)
        if len(groupwatches) == 0:
            return await ctx.send("No active groupwatches in the list, create one with `gw create`")
        threads = []
        for groupwatch in groupwatches:
            threads.append(await self.bot.fetch_channel(groupwatch.get("thread_id")))
        archive = ArchiveSelectView(threads, ctx.author)
        await ctx.send("Choose a groupwatch to archive", view=archive)
        await archive.wait()
        if archive.chosen:
            await self.bot.db.execute("""
            DELETE FROM groupwatches WHERE thread_id = $1
            """, archive.chosen)
            thread = await self.bot.fetch_channel(archive.chosen)
            await thread.edit(archived=True)


        


def setup(bot):
    bot.add_cog(GroupWatch(bot))
