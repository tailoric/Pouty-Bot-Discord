from datetime import datetime, timedelta, timezone
from functools import reduce
import textwrap
from discord.ext import commands, tasks
from discord import app_commands
import discord
import numpy as np
from discord.utils import find, utcnow
from .utils.checks import is_owner_or_moderator
from .utils.converters import ReferenceOrMessage, TimeConverter
from typing import Any, Dict, Literal, Optional, List, Set, TypedDict, Union, Sequence
import re
from uuid import UUID, uuid4
from dataclasses import dataclass, field
import itertools
import asyncpg
import matplotlib.pyplot as plt
import io
import logging

timing_regex = re.compile(r"^(?P<days>\d+\s?d(?:ay)?s?)?\s?(?P<hours>\d+\s?h(?:our)?s?)?\s?(?P<minutes>\d+\s?m(?:in(?:ute)?s?)?)?\s?(?P<seconds>\d+\s?s(?:econd)?s?)?")

class TimeCodeConversionError(app_commands.AppCommandError):
    pass

def transform_time(argument: str) -> datetime:
        match = timing_regex.match(argument)
        if not match:
            raise TimeCodeConversionError("Could not transform duration")
        if not any(match.groupdict().values()):
            raise TimeCodeConversionError("Could not transform duration")
        timer_inputs = match.groupdict()
        for key, value in timer_inputs.items():
            if value is None:
                value = 0
            else:
                value = int(''.join(filter(str.isdigit, value)))
            timer_inputs[key] = value
        delta = timedelta(**timer_inputs)
        return datetime.now(timezone.utc) + delta

class TimeTransformer(app_commands.Transformer):

    @classmethod
    async def transform(cls, interaction: discord.Interaction, argument: str) -> datetime:
        return transform_time(argument)

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
    anonymous : bool
    message: Union[discord.Message, discord.PartialMessage, None] = None
    options: List[PollOption] = field(default_factory=list)
    votes: Dict[int, Set[PollVote]] = field(default_factory=dict)
    should_update = False
    finished = False
    description: Optional[str] = None

    @tasks.loop(seconds=2)
    async def update_count(self):
        if self.should_update:
            if isinstance(self.message, discord.InteractionMessage) or isinstance(self.message, discord.PartialMessage):
                self.message = await self.message.fetch()
            await self.message.edit(embed=self.embed)
            self.should_update = False
    @property
    def embed(self):
        description = self.description
        if not description:
            description = f"Vote for your favourite option{'s' if self.type == 'multi' else ''} via the dropdown below\nEnds {discord.utils.format_dt(self.end_date, 'R')}"
        else:
            description += f"\nEnds in {discord.utils.format_dt(self.end_date, 'R')}"
        embed = discord.Embed(title=self.title, description=description)
        embed.set_author(name=self.creator.display_name, icon_url=self.creator.display_avatar)
        for option in self.options:
            embed.add_field(name=option.text, value=self.get_vote_count(option), inline=False)
        return embed
    
    def get_vote_count(self, option: PollOption):
        if self.votes:
            count = 0
            for votes in self.votes.values():
                for _ in filter(lambda v: v.option.id == option.id , votes):
                    count = count + 1
            return count
        else: 
            return 0

    @classmethod
    def from_database_entries(cls, bot: commands.Bot, entries: List):
        first = next(iter(entries), None)
        if first:
            guild=bot.get_guild(first.get("guild_id"))
            channel = guild.get_channel(first.get("channel_id")) or bot.get_partial_messageable(first.get("channel_id"))
            return cls(
                    id=first.get("poll_id"),
                    title=first.get("title"),
                    type=first.get("type"),
                    guild=guild,
                    channel=channel,   
                    anonymous=first.get("anonymous"),
                    creator=guild.get_member(first.get("creator_id")),
                    message=channel.get_partial_message(first.get("message_id")),
                    end_date=first.get("end_date"),
                    options=[PollOption(id=o.get("option_id"), text=o.get("text")) for o in entries]
                    )

    async def create_in_store(self, db: Union[asyncpg.Connection, asyncpg.Pool]):
        await db.execute('''
        INSERT INTO poll.data (poll_id, channel_id, message_id, guild_id, creator_id, type, title, end_date, anonymous ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ''', self.id, self.channel.id, self.message.id, self.guild.id, self.creator.id, self.type, self.title, self.end_date, self.anonymous)
        await db.executemany('''
        INSERT INTO poll.option VALUES ($1, $2, $3)
        ''', [(opt.id, opt.text, self.id) for opt in self.options]
        )
    def add_options(self, options: List[PollOption]) -> None:
        if self.options:
            self.options.extend(options)
        else:
            self.options = options

    def add_vote(self, vote: PollVote) -> None:
        user_id = vote.user.id
        if user_id not in self.votes: 
            self.votes[user_id] = set()

        if self.type == "single":
            self.votes[user_id] = set([vote])
            return
        if self.type == "multi":
            self.votes[user_id].add(vote)
        self.should_update = True

    async def sync_votes(self, db: Union[asyncpg.Pool, asyncpg.Connection]):
        for user_id, votes in self.votes.items():
            await db.execute("""
                DELETE FROM poll.vote WHERE user_id = $1 AND poll = $2;
            """, user_id, self.id)
            await db.executemany("""
                INSERT INTO poll.vote VALUES ($1, $2, $3, $4)
            """, [(uuid4(), vote.user.id, vote.option.id, self.id) for vote in votes])

    async def finish(self, db: Union[asyncpg.Pool, asyncpg.Connection], interaction: Optional[discord.Interaction]):
        embed = self.embed
        description = f"{self.description if self.description else ''}\nResults:\n"
        embed.clear_fields()
        embed.set_image(url="attachment://result.png")
        labels = []
        counts = []
        for option in self.options:
            count =self.get_vote_count(option)
            if count > 0:
                labels.append(option.text)
                counts.append(count)
        if counts:
            results = list(sorted(zip(counts, labels), reverse=True))
            description += '\n'.join(f'`{r[1]}: {r[0]}`' for r in results)
            embed.description = description
            fig, ax = plt.subplots()
            counts = [r[0] for r in results]
            winners = [0.1 if c == max(counts) else 0.0 for c in counts]
            ax.pie(list(map(lambda c: c[0]/sum(counts), results)),labels=[r[1] for r in results], explode=winners, autopct='%1.1f%%')
            ax.set_title(self.title)
            buffer = io.BytesIO()
            fig.savefig(buffer, format='png')
            buffer.seek(0)
            f = discord.File(buffer, filename='result.png')
            if interaction:
                await interaction.response.send_message(embed=embed, file=f)
            else:
                await self.message.reply(embed=embed, file=f)
            plt.close(fig)
        else:
            if interaction:
                await interaction.response.send_message("Poll finished without any votes")
            elif self.message:
                await self.message.reply(content="Poll finished without any votes")

        await self.message.edit(embed=self.embed, view=None)
        await db.execute("""
        DELETE FROM poll.data WHERE poll_id = $1
        """, self.id)
        self.finished = True
        self.update_count.stop()

class DurationChangeModal(discord.ui.Modal):

    time_input = discord.ui.TextInput(label="New Duration", placeholder="Format: 2h3m14s")


    def __init__(self, *, title: str = ..., timeout: Optional[float] = None, view: 'PollCreateMenu') -> None:
        self.duration = None
        self.view = view
        super().__init__(title=title, timeout=timeout)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.time_input.value:
            try:
                self.duration = transform_time(self.time_input.value)
                self.view.poll.end_date = self.duration
                await interaction.response.edit_message(embed=self.view.embed, view=self.view)
            except TimeCodeConversionError as e:
                await interaction.response.send_message(e, ephemeral=True)
        else:
            await interaction.response.send_message("No Time input provided", ephemeral=True)

class PollCreateMenu(discord.ui.View):
    def __init__(self, *, poll: PollData, bot: commands.Bot):
        self.poll = poll
        self.bot = bot
        self.message: Optional[discord.Message] = None
        super().__init__(timeout=None)


    @discord.ui.button(label="Add Options", emoji="\N{HEAVY PLUS SIGN}")
    async def more_opts_btn(self, inter: discord.Interaction, btn: discord.ui.Button):
        poll = PollModal(bot=self.bot, title=self.poll.title, start=len(self.poll.options))
        await inter.response.send_modal(poll)
        await poll.wait()
        self.poll.add_options(options=poll.created_options)
        menu_message = await inter.original_response()
        if len(self.poll.options) >= 2:
            self.create_poll.disabled = False
        if len(self.poll.options) >= 25:
            self.poll.options = self.poll.options[:25]
            self.more_opts_btn.disabled = True
        await menu_message.edit(embed=self.embed, view=self)

    @discord.ui.button(label="Reset Options", row=0)
    async def reset_options(self, inter: discord.Interaction, btn: discord.ui.Button):
        self.poll.options.clear()
        self.create_poll.disabled = True
        await inter.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(label="Start Poll", style=discord.ButtonStyle.green, disabled=True, row=2)
    async def create_poll(self, inter: discord.Interaction, btn: discord.ui.Button):
        poll_view = PollView(bot=self.bot, poll=self.poll)
        await inter.response.send_message(embed=self.poll.embed, view=poll_view)
        self.poll.message = await inter.original_response()
        await self.poll.create_in_store(db=self.bot.db)
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message:
            await self.message.delete()
        self.stop()
        
    @discord.ui.button(label="Toggle Anonymous", emoji="\N{SLEUTH OR SPY}\N{VARIATION SELECTOR-16}", row=1)
    async def toggle_anon(self, inter: discord.Interaction, btn: discord.ui.Button):
        self.poll.anonymous = not self.poll.anonymous
        await inter.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(label="Change Duration", emoji="\N{CLOCK FACE ONE OCLOCK}", row=1)
    async def change_duration(self, inter: discord.Interaction, btn: discord.ui.Button):
        time_modal = DurationChangeModal(title="Change Duration", timeout=60, view=self)
        await inter.response.send_modal(time_modal)

    @property
    def embed(self):
        embed = discord.Embed(title=self.poll.title, description="This is an interactive menu to add options to your poll use the +Options button to add vote options to the poll")
        for idx,option in enumerate(self.poll.options):
            embed.add_field(name=idx+1, value=option.text, inline=False)
        embed.add_field(name="Anonymous Votes", value="\N{WHITE HEAVY CHECK MARK}" if self.poll.anonymous else "\N{CROSS MARK}", inline=False)
        embed.add_field(name="Ends", value=discord.utils.format_dt(self.poll.end_date, "R"), inline=False)
        return embed

    async def start(self, interaction: discord.Interaction):
        self.interaction = interaction
        await interaction.response.send_message(embed=self.embed, view=self, ephemeral=True)
        self.message = await interaction.original_response()


class VotesView(discord.ui.View):
    def __init__(self, *, timeout: Optional[float] = 180, poll: PollData):
        self.poll = poll
        self._page = 0
        super().__init__(timeout=timeout)

    @property
    def embed(self):
        _embed = discord.Embed(description="")
        option = self.poll.options[self._page]
        _embed.title = f"Votes for {option.text}"
        for user, votes in self.poll.votes.items():
            if option.id in [vote.option.id for vote in votes]:
                _embed.description += f"<@{user}>,"
        _embed.description = _embed.description[:-1]
        _embed.description = textwrap.shorten(_embed.description, 4000)
        return _embed

    @discord.ui.button(emoji="\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}")
    async def _prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._page = max(self._page -1, 0)
        await interaction.response.edit_message(view=self, embed=self.embed)

    @discord.ui.button(emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}")
    async def _next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._page = min(self._page +1, len(self.poll.options) -1)
        await interaction.response.edit_message(view=self, embed=self.embed)


class VoterButton(discord.ui.Button):
    
    def __init__(self, *, poll: PollData, bot):
        self.poll = poll
        self.bot = bot
        super().__init__(label="Show Votes", emoji="\N{EYES}", custom_id=f"{poll.id}-voters")

    async def callback(self, interaction: discord.Interaction) -> Any:
        view = VotesView(poll=self.poll) 
        await interaction.response.send_message(ephemeral=True, view=view, embed=view.embed)
                

class TimerButton(discord.ui.Button):
    def __init__(self, *, poll: PollData):
        self.poll = poll
        super().__init__(style=discord.ButtonStyle.gray, emoji="\N{HOURGLASS}", custom_id=f"{poll.id}-timer", label="Duration")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Poll ends in: {discord.utils.format_dt(self.poll.end_date, style='R')}", ephemeral=True)

class EndPollButton(discord.ui.Button):
    def __init__(self, *, bot: commands.Bot, poll: PollData):
        self.bot = bot
        self.poll = poll
        super().__init__(style=discord.ButtonStyle.gray, emoji="\N{BLACK SQUARE FOR STOP}\N{VARIATION SELECTOR-16}", custom_id=f"{poll.id}-close", label="End Poll")

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id == self.poll.creator.id:
            await self.poll.finish(self.bot.db, interaction=interaction)
        else:
            await interaction.response.send_message("You can't close that poll since it is not yours", ephemeral=True)

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
            self.poll.add_vote(PollVote(id=uuid4(), user=interaction.user, option=option))
        await self.poll.sync_votes(self.bot.db)
        await interaction.response.send_message(content=f"Voted for {','.join('`'+v.option.text+'`' for v in self.poll.votes[interaction.user.id])}", ephemeral=True)
        self.poll.should_update = True
        if not self.poll.update_count.is_running():
            self.poll.update_count.start()

class PollView(discord.ui.View):
    def __init__(self, *, bot, poll: PollData):
        super().__init__(timeout=None)
        self.bot = bot
        self.poll = poll
        self.select = PollOptionSelect(bot=bot, poll=poll)
        self.end_button = EndPollButton(bot=bot, poll=poll)
        self.add_item(self.select)
        if not poll.anonymous:
            self.voter_button = VoterButton(poll=poll, bot=bot)
            self.add_item(self.voter_button)
        self.timer_button = TimerButton(poll=poll)
        self.add_item(self.end_button)
        self.add_item(self.timer_button)

class PollModal(discord.ui.Modal):

    def __init__(self, *, bot: commands.Bot, title="Poll Title", start=0) -> None:
        self.bot = bot
        self.created_options : List[PollOption]= []
        super().__init__(title=title if len(title) < 25 else "Add Options", timeout=None)
        for i in range(start, start+5):
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
        self.open_polls: List[PollData] = []


    @tasks.loop(minutes=1)
    async def check_poll_status(self):
        finished_polls = []
        for poll in self.open_polls:
            if poll.finished:
                finished_polls.append(poll)
            elif poll.end_date < datetime.now(tz=timezone.utc):
                await poll.finish(self.bot.db, interaction=None)
                finished_polls.append(poll)
            elif self.check_poll_status.next_iteration and poll.end_date < self.check_poll_status.next_iteration:
                self.bot.loop.create_task(self.finish_up_poll(poll))
                finished_polls.append(poll)
        for poll in finished_polls:
            self.open_polls.remove(poll)


    async def finish_up_poll(self, poll):
        await discord.utils.sleep_until(poll.end_date)
        await poll.finish(self.bot.db, interaction=None)


    async def cog_load(self):
        await self.create_database()
        await self.load_views()
        self.check_poll_status.start()
    async def cog_unload(self):
        self.check_poll_status.stop()

    async def load_views(self):
        polls = await self.bot.db.fetch("SELECT * FROM poll.data dt JOIN poll.option o on dt.poll_id = o.poll")
        for poll_id, data in itertools.groupby(polls, lambda p: p.get("poll_id")):
            poll = PollData.from_database_entries(self.bot, list(data))
            if not poll:
                continue
            votes = await self.bot.db.fetch("SELECT * FROM poll.vote WHERE poll = $1", poll_id)
            for vote in votes:
                option = next(filter(lambda opt: opt.id == vote.get("option"), poll.options))
                vote = PollVote(vote.get("vote_id"), user=discord.Object(vote.get("user_id")), option=option)
                poll.add_vote(vote=vote)
            self.bot.add_view(PollView(bot=self.bot,poll=poll))
            self.open_polls.append(poll)
         

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
                anonymous boolean NOT NULL DEFAULT true,
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
    @app_commands.describe(description="Default 24 hours. Describe the purpose of this poll")
    @app_commands.describe(anonymous="Default True. Set if votes should be hidden or openly visible")
    @app_commands.describe(duration="Default 24 hours. Set how long the poll should go")
    async def poll_single(self, interaction: discord.Interaction,
            title: app_commands.Range[str, 1, 255],
            description: Optional[str],
            duration: app_commands.Transform[Optional[datetime], TimeTransformer] = None,
            anonymous: bool = True
            ):
        """
        Creates an interactive menu for generating a single choice poll
        """
        if not duration:
            duration = datetime.now(tz=timezone.utc) + timedelta(hours=24)
        poll_data = PollData(uuid4(), title=title, channel=interaction.channel, guild=interaction.guild, creator=interaction.user, type="single", end_date=duration, description=description, anonymous=anonymous)
        menu = PollCreateMenu(bot=self.bot, poll=poll_data)
        await menu.start(interaction=interaction)
        await menu.wait()
        self.open_polls.append(menu.poll)


    @poll.command(name="multi")
    @app_commands.describe(title="The title of the Poll")
    @app_commands.describe(description="Describe the purpose of this poll")
    @app_commands.describe(duration="Default 24 hours. Set how long the poll should go")
    @app_commands.describe(anonymous="Default True. Set if votes should be hidden or openly visible")
    async def poll_multi(self, interaction: discord.Interaction,
            title: app_commands.Range[str, 1, 255],
            description: Optional[str],
            duration: app_commands.Transform[Optional[datetime], TimeTransformer] = None,
            anonymous: bool = True
            ):
        """
        Creates an interactive menu for generating a multi choice poll
        """
        if not duration:
            duration = datetime.now(tz=timezone.utc) + timedelta(hours=24)
        poll_data = PollData(uuid4(), title=title, channel=interaction.channel, guild=interaction.guild, creator=interaction.user, type="multi", end_date=duration, description=description, anonymous=anonymous)
        menu = PollCreateMenu(bot=self.bot, poll=poll_data)
        await menu.start(interaction=interaction)
        await menu.wait()
        self.open_polls.append(menu.poll)
    

async def setup(bot):
    await bot.add_cog(Poll(bot))
