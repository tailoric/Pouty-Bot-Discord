from datetime import datetime, timedelta
from discord.ext import commands, tasks
from discord import Embed, Message, NotFound, Forbidden, HTTPException, app_commands
import discord
from discord.utils import find, utcnow
from .utils.checks import is_owner_or_moderator
from .utils.converters import ReferenceOrMessage, TimeConverter
from typing import Literal, Optional, List, TypedDict, Union, Sequence
import logging
import re
import asyncpg
from uuid import UUID, uuid4
from dataclasses import dataclass, field

timing_regex = re.compile(r"^(?P<days>\d+\s?d(?:ay)?s?)?\s?(?P<hours>\d+\s?h(?:our)?s?)?\s?(?P<minutes>\d+\s?m(?:in(?:ute)?s?)?)?\s?(?P<seconds>\d+\s?s(?:econd)?s?)?")


@dataclass(frozen=True)
class PollOption:
    id: UUID
    text: str
    
@dataclass(frozen=True)
class PollVote:
    id: UUID
    user: Union[int, discord.User]
    option: PollOption

@dataclass
class PollData:
    id: UUID
    title: str
    type: Literal["single","multi"]
    channel: Union[int, discord.TextChannel, discord.VoiceChannel]
    guild: Union[int, discord.Guild]
    creator: Union[int, discord.User, discord.Member]
    end_date: datetime
    message: Union[int, discord.Message, None] = None
    options: List[PollOption] = field(default_factory=list)
    votes: dict = field(default_factory=dict)

    async def add_vote(self, vote: PollVote):
        user_id = vote.user.id
        if user_id not in self.votes: 
            self.votes[user_id] = set()

        if self.type == "single":
            self.votes[user_id] = set([vote])
            return
        if self.type == "multi":
            self.votes[user_id].add(vote)

    async def sync_votes(self, db):
        for user_id, votes in self.votes.items():
            await db.execute("""
                DELETE FROM poll.vote WHERE user_id = $1;
            """, user_id)
            await db.executemany("""
                INSERT INTO poll.vote VALUES ($1, $2, $3, $4)
            """, [(uuid4(), vote.user.id, vote.option.id, self.poll.id) for vote in votes])


class PollOptionSelect(discord.ui.Select):
    def __init__(self, *, bot: commands.Bot, poll: PollData) -> None:
        self.bot = bot
        self.poll = poll
        self.is_multi = poll.type == "multi"
        max_values = 1
        if self.is_multi:
            max_values = len(poll.options) - 1
        super().__init__(placeholder="Choose an option to vote on", max_values=max_values, row=0, custom_id=f"{poll.id}:select")
        for option in poll.options:
            self.add_option(label=option.text, value=str(option.id))

    async def callback(self, interaction: discord.Interaction):
        if self.is_multi:
            self.poll.votes[interaction.user.id] = set()
        for selection in self.values:
            option = next(filter(lambda o: o.id == UUID(selection) , self.poll.options))
            await self.poll.add_vote(PollVote(id=uuid4(), user=interaction.user, option=option))
        await self.poll.sync_votes(self.bot.db)
        await interaction.response.send_message(content=f"Voted for {[v.option.text for v in self.poll.votes[interaction.user.id]]}", ephemeral=True)


class PollView(discord.ui.View):
    def __init__(self, *, bot, poll: PollData):
        super().__init__(timeout=None)
        self.bot = bot
        self.options = []
        self.select = PollOptionSelect(bot=bot, poll=poll)
        self.add_item(self.select)

class PollModal(discord.ui.Modal):

    def __init__(self, *, bot: commands.Bot, num_options, poll_data: PollData) -> None:
        self.poll_data = poll_data
        self.num_options = num_options
        self.is_multi = poll_data.type == "multi"
        self.bot = bot
        super().__init__(title=poll_data.title, timeout=None)
        for i in range(1, num_options+1):
            txt_input = discord.ui.TextInput(label=f"Option {i}")
            self.add_item(txt_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title=self.title)
        for idx,txt_input in enumerate(self.children):
            self.poll_data.options.append(PollOption(uuid4(), txt_input.value))
            embed.add_field(name=idx+1, value=txt_input.value, inline=False)
        await interaction.response.send_message(embed=embed, view=PollView(bot=self.bot, poll=self.poll_data))
        self.poll_data.message = await interaction.original_message()
        await self.bot.db.execute('''
        INSERT INTO poll.data VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ''', self.poll_data.id, self.poll_data.channel.id, self.poll_data.message.id, self.poll_data.guild.id, self.poll_data.creator.id, self.poll_data.type, self.poll_data.title, self.poll_data.end_date)
        await self.bot.db.executemany('''
        INSERT INTO poll.option VALUES ($1, $2, $3)
        ''', [(opt.id, opt.text, self.poll_data.id) for opt in self.poll_data.options]
        )
class Poll(commands.Cog):

    def __init__(self, bot):
        self.bot = bot


    async def cog_load(self):
        await self.create_database()
        await self.load_views()
    async def cog_unload(self):
        pass

    async def load_views(self):
        polls = await self.bot.db.fetch("SELECT * FROM poll.data dt JOIN poll.vote v on ")


    async def create_database(self):
        query = """
            CREATE SCHEMA IF NOT EXISTS poll;
            CREATE TABLE IF NOT EXISTS poll.data (
                poll_id UUID PRIMARY KEY,
                channel_id BIGINT,
                message_id BIGINT,
                guild_id BIGINT,
                creator_id BIGINT,
                type TEXT,
                title TEXT,
                end_date TIMESTAMP WITH TIME ZONE
            );
            CREATE TABLE IF NOT EXISTS poll.option(
                option_id UUID PRIMARY KEY,
                text TEXT,
                poll UUID REFERENCES poll.data (poll_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS poll.vote (
                vote_id UUID PRIMARY KEY,
                user_id BIGINT,
                option UUID REFERENCES poll.option (option_id) ON DELETE CASCADE,
                poll UUID REFERENCES poll.data (poll_id) ON DELETE CASCADE
            );
        """
        await self.bot.db.execute(query)

    poll = app_commands.Group(name="poll", description="Commands for creating polls")

    @poll.command(name="single")
    @app_commands.describe(title="The title of the Poll")
    @app_commands.describe(options="Number of poll options")
    async def poll_single(self, interaction: discord.Interaction, title: str, options: app_commands.Range[int, 2, 25]):
        """
        create a single choice poll
        """
        poll_data = PollData(uuid4(), title=title, channel=interaction.channel, guild=interaction.guild, creator=interaction.user, type="single", end_date=discord.utils.utcnow() + timedelta(minutes=5))
        poll = (PollModal(bot=self.bot, poll_data=poll_data, num_options=options))
        await interaction.response.send_modal(poll)

    @poll.command(name="multi")
    @app_commands.describe(title="The title of the Poll")
    @app_commands.describe(options="Number of poll options")
    async def poll_multi(self, interaction: discord.Interaction, title: str, options: app_commands.Range[int, 3, 25]):
        """
        create a single choice poll
        """
        poll_data = PollData(uuid4(), title=title, channel=interaction.channel, guild=interaction.guild, creator=interaction.user, type="multi", end_date=discord.utils.utcnow() + timedelta(minutes=5))
        poll = (PollModal(bot=self.bot, poll_data=poll_data, num_options=options))
        await interaction.response.send_modal(poll)

    

async def setup(bot):
    await bot.add_cog(Poll(bot))
