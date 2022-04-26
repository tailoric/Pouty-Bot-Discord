from datetime import datetime, timedelta
from discord.ext import commands, tasks
from discord import Embed, Message, NotFound, Forbidden, HTTPException, app_commands
import discord
from discord.utils import find, utcnow
from .utils.checks import is_owner_or_moderator
from .utils.converters import ReferenceOrMessage, TimeConverter
from typing import Literal, Optional, List, TypedDict, Union, Sequence
import re
from uuid import UUID, uuid4
from dataclasses import dataclass, field
import itertools
import asyncpg

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
    creator: Union[discord.User, discord.Member]
    end_date: datetime
    message: Union[discord.Message, discord.PartialMessage, None] = None
    options: List[PollOption] = field(default_factory=list)
    votes: dict = field(default_factory=dict)

    @classmethod
    def from_database_entries(cls, bot: commands.Bot, entries: List):
        first = next(iter(entries), None)
        if first:
            guild=bot.get_guild(first.get("guild_id"))
            channel = guild.get_channel(first.get("channel_id"))
            return cls(
                    id=first.get("poll_id"),
                    title=first.get("title"),
                    type=first.get("type"),
                    guild=guild,
                    channel=channel,   
                    creator=guild.get_member(first.get("creator_id")),
                    message=channel.get_partial_message(first.get("message_id")),
                    end_date=first.get("end_date"),
                    options=[PollOption(id=o.get("option_id"), text=o.get("text")) for o in entries]
                    )

    async def create_in_store(self, db: Union[asyncpg.Connection, asyncpg.Pool]):
        await db.execute('''
        INSERT INTO poll.data VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ''', self.id, self.channel.id, self.message.id, self.guild.id, self.creator.id, self.type, self.title, self.end_date)
        await db.executemany('''
        INSERT INTO poll.option VALUES ($1, $2, $3)
        ''', [(opt.id, opt.text, self.id) for opt in self.options]
        )
    async def add_options(self, db: Union[asyncpg.Connection, asyncpg.Pool], options: List[PollOption]) -> None:
        if self.options:
            self.options.extend(options)
        else:
            self.options = options

    async def add_vote(self, vote: PollVote) -> None:
        user_id = vote.user.id
        if user_id not in self.votes: 
            self.votes[user_id] = set()

        if self.type == "single":
            self.votes[user_id] = set([vote])
            return
        if self.type == "multi":
            self.votes[user_id].add(vote)

    async def sync_votes(self, db: Union[asyncpg.Pool, asyncpg.Connection]):
        for user_id, votes in self.votes.items():
            await db.execute("""
                DELETE FROM poll.vote WHERE user_id = $1;
            """, user_id)
            await db.executemany("""
                INSERT INTO poll.vote VALUES ($1, $2, $3, $4)
            """, [(uuid4(), vote.user.id, vote.option.id, self.id) for vote in votes])


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


class PollCreateMenu(discord.ui.View):
    def __init__(self, *, poll: PollData, bot: commands.Bot):
        self.poll = poll
        self.bot = bot
        self.interaction: Optional[discord.Interaction] = None
        super().__init__(timeout=None)


    @discord.ui.button(label="+Options")
    async def more_opts_btn(self, inter: discord.Interaction, btn: discord.ui.Button):
        poll = PollModal(bot=self.bot, title=self.poll.title)
        await inter.response.send_modal(poll)
        await poll.wait()
        await self.poll.add_options(db=self.bot.db, options=poll.created_options)
        menu_message = await inter.original_message()
        await menu_message.edit(embed=self.embed, view=self)

    @discord.ui.button(label="Start Poll", style=discord.ButtonStyle.green)
    async def create_poll(self, inter: discord.Interaction, btn: discord.ui.Button):
        await self.poll.create_in_store(db=self.bot.db)
        poll_view = PollView(bot=self.bot, poll=self.poll)
        await inter.response.send_message(embed=self.embed, view=poll_view)
        
    @property
    def embed(self):
        embed = discord.Embed(title=self.poll.title)
        for idx,option in enumerate(self.poll.options):
            embed.add_field(name=idx+1, value=option.text, inline=False)

        return embed

    async def start(self, interaction: discord.Interaction):
        self.interaction = interaction
        await interaction.response.send_message(embed=self.embed, view=self, ephemeral=True)
        self.poll.message = await interaction.original_message()

class PollView(discord.ui.View):
    def __init__(self, *, bot, poll: PollData):
        super().__init__(timeout=None)
        self.bot = bot
        self.select = PollOptionSelect(bot=bot, poll=poll)
        self.add_item(self.select)

class PollModal(discord.ui.Modal):

    def __init__(self, *, bot: commands.Bot, title="Poll Title") -> None:
        self.bot = bot
        self.created_options : List[PollOption]= []
        super().__init__(title=title, timeout=None)
        for i in range(0, 5):
            txt_input = discord.ui.TextInput(label=f"Option {i+1}", required=False, style=discord.TextStyle.short, max_length=100)
            self.add_item(txt_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        for child in self.children:
            if child.value:
                self.created_options.append(PollOption(uuid4(), child.value))
        self.stop()

class Poll(commands.Cog):

    def __init__(self, bot):
        self.bot = bot


    async def cog_load(self):
        await self.create_database()
        await self.load_views()
    async def cog_unload(self):
        pass

    async def load_views(self):
        polls = await self.bot.db.fetch("SELECT * FROM poll.data dt JOIN poll.option o on dt.poll_id = o.poll")
        for poll_id, data in itertools.groupby(polls, lambda p: p.get("poll_id")):
            poll = PollData.from_database_entries(self.bot, list(data))
            self.bot.add_view(PollView(bot=self.bot,poll=poll))
         

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
        menu = PollCreateMenu(bot=self.bot, poll=poll_data)
        await menu.start(interaction=interaction)


    @poll.command(name="multi")
    @app_commands.describe(title="The title of the Poll")
    @app_commands.describe(options="Number of poll options")
    async def poll_multi(self, interaction: discord.Interaction, title: str, options: app_commands.Range[int, 3, 25]):
        """
        create a single choice poll
        """
        poll_data = PollData(uuid4(), title=title, channel=interaction.channel, guild=interaction.guild, creator=interaction.user, type="multi", end_date=discord.utils.utcnow() + timedelta(minutes=5))
        menu = PollCreateMenu(bot=self.bot, poll=poll_data)
        await menu.start(interaction=interaction)

    

async def setup(bot):
    await bot.add_cog(Poll(bot))
