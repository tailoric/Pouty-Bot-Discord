from datetime import datetime, timedelta
from discord.ext import commands, tasks
from discord import Embed, Message, NotFound, Forbidden, HTTPException
from discord.utils import find, utcnow
from .utils.checks import is_owner_or_moderator
from .utils.converters import ReferenceOrMessage, TimeConverter
from typing import Optional, List
import logging
import re

timing_regex = re.compile(r"^(?P<days>\d+\s?d(?:ay)?s?)?\s?(?P<hours>\d+\s?h(?:our)?s?)?\s?(?P<minutes>\d+\s?m(?:in(?:ute)?s?)?)?\s?(?P<seconds>\d+\s?s(?:econd)?s?)?")


class PollFlags(commands.FlagConverter):
    title: str
    duration: TimeConverter
    options: List[str] = commands.flag(name="option", aliases=['o'], max_args=10)

class Poll(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.create_database())
        self.check_polls.start()
        self.option_labels = [
                    "\N{DIGIT ONE}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}",
                    "\N{DIGIT TWO}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}",
                    "\N{DIGIT THREE}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}",
                    "\N{DIGIT FOUR}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}",
                    "\N{DIGIT FIVE}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}",
                    "\N{DIGIT SIX}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}",
                    "\N{DIGIT SEVEN}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}",
                    "\N{DIGIT EIGHT}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}",
                    "\N{DIGIT NINE}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}",
                    "\N{KEYCAP TEN}"
                ]

    def cog_unload(self):
        self.check_polls.cancel()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        poll = await self.fetch_poll(payload.message_id)
        if not poll:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if payload.user_id == guild.me.id:
            return
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        for reaction in message.reactions:
            if reaction.emoji not in self.option_labels:
                await reaction.clear()
                continue
            if reaction.emoji == payload.emoji.name:
                continue
            user = await reaction.users().find(lambda u: u.id == payload.member.id)
            if user and not poll.get("multi"):
                await reaction.remove(user)

    @tasks.loop(seconds=5.0)
    async def check_polls(self):
        polls = await self.fetch_polls()
        if not polls:
            return
        for poll in polls:
            if poll.get("end_ts") > datetime.utcnow():
                continue
            try:
                poll_channel = self.bot.get_channel(poll.get("channel_id"))
                poll_msg = await poll_channel.fetch_message(poll.get("message_id"))
                reactions = poll_msg.reactions
                options = poll_msg.embeds[0].description.splitlines()
                reactions = sorted(reactions, key=lambda r: r.count, reverse=True)
                valid_reacts = list(filter(lambda r: r.emoji in self.option_labels, reactions))
                top_count = valid_reacts[0].count
                winners = list(filter(lambda r: r.count == top_count , valid_reacts))
                embed = poll_msg.embeds[0]
                winner_text = [t for t in options for w in winners if t.startswith(w.emoji)]
                win_embed = Embed(title="Poll finished")
                win_embed.add_field(name="Title", value=poll_msg.embeds[0].title, inline=False)
                for w in winner_text:
                    win_embed.add_field(name="Winner", value=w[5:])
                    embed.add_field(name="Winner", value=w[5:])
                win_embed.add_field(name="jump to", value=f"[poll]({poll_msg.jump_url})", inline=False)
                await poll_channel.send(embed=win_embed)
                await poll_msg.edit(embed=embed)
                await self.delete_poll(poll_msg.id)
            except (NotFound, Forbidden, HTTPException) as e:
                logger = logging.getLogger("PoutyBot")
                logger.error("error in the poll loop, message_id: %s, channel_id: %s ",poll.get("message_id"), poll.get("channel_id"),exc_info=1)
                await self.delete_poll(poll.get("message_id"))
            except:
                logger = logging.getLogger("PoutyBot")
                logger.error("error in the poll loop, message_id: %s, channel_id: %s ",poll.get("message_id"), poll.get("channel_id"),exc_info=1)


    async def create_database(self):
        query = """
            CREATE TABLE IF NOT EXISTS polls (
                message_id BIGINT PRIMARY KEY,
                channel_id BIGINT,
                end_ts TIMESTAMP WITH TIME ZONE,
                multi BOOLEAN
                )
        """
        await self.bot.db.execute(query)

    async def insert_poll(self, message_id: int, channel_id: int, end: datetime, multi=False):
        async with self.bot.db.acquire() as con:
            query = """
                INSERT INTO polls (message_id, channel_id, end_ts, multi)VALUES ($1, $2, $3, $4)
            """
            statement = await con.prepare(query)
            async with con.transaction():
                await statement.fetch(message_id, channel_id, end, multi)

    async def fetch_poll(self, message_id):
        async with self.bot.db.acquire() as con:
            query = """
                SELECT message_id, channel_id, end_ts, multi
                FROM polls
                WHERE message_id = $1
            """
            statement = await con.prepare(query)
            async with con.transaction():
                return await statement.fetchrow(message_id)

    async def fetch_polls(self):
        async with self.bot.db.acquire() as con:
            query = """
                SELECT message_id, channel_id, end_ts
                FROM polls
            """
            statement = await con.prepare(query)
            async with con.transaction():
                return await statement.fetch()

    async def delete_poll(self, message_id):
        async with self.bot.db.acquire() as con:
            query = """
                DELETE FROM polls WHERE message_id = $1
            """
            statement = await con.prepare(query)
            async with con.transaction():
                await statement.fetch(message_id)

    @commands.group(invoke_without_command=True, usage="poll `title:` Title of Poll `duration:` 24h `option:` option 1 `o:` option 2")
    async def poll(self, ctx, *, flags: PollFlags):
        """
        create a single choice poll (at most 10 choices possible)
        **flags**:
        `title:` The title of the poll
        `duration:` the duration of the poll (`2 days 4 hours` for example) can accept days hours minutes and seconds
        `o[ption]:` the poll options flag can be written short with `o:` every option must preceed with this flag
        example `option: option number 1 o: option number 2`

        """
        if ctx.invoked_subcommand:
            return
        end_timestamp = flags.duration
        if not end_timestamp:
            return await ctx.send("incorrect time format: a valid example is `2d20h30m10s` for 2 days 20 hours 30 minutes and 10 seconds")
        if len(flags.options) > 10:
            return await ctx.send("No more than 10 choices allowed!")
        description = ''
        reactions = []
        for index, option in enumerate(flags.options):
            reactions.append(self.option_labels[index])
            description += f"{self.option_labels[index]}: {option}\n"
        embed = Embed(
                    title=flags.title,
                    description=description
                )
        poll_msg = await ctx.send(embed=embed)
        for reaction in reactions:
            await poll_msg.add_reaction(reaction)
        await self.insert_poll(poll_msg.id, poll_msg.channel.id, end_timestamp)

    @poll.command(usage="poll multi `title:` Title of Poll `duration:` 24h `option:` option 1 `o:` option 2")
    async def multi(self, ctx, title, * ,flags: PollFlags):
        """
        create a multiple choice poll
        """
        if ctx.invoked_subcommand:
            return
        end_timestamp = flags.duration
        if not end_timestamp:
            return await ctx.send("incorrect time format: a valid example is `2d20h30m10s` for 2 days 20 hours 30 minutes and 10 seconds")
        if len(flags.options) > 10:
            return await ctx.send("No more than 10 choices allowed!")
        description = ''
        reactions = []
        for index, option in enumerate(flags.options):
            reactions.append(self.option_labels[index])
            description += f"{self.option_labels[index]}: {option}\n"
        embed = Embed(
                    title=title,
                    description=description
                )
        poll_msg = await ctx.send(embed=embed)
        for reaction in reactions:
            await poll_msg.add_reaction(reaction)
        await self.insert_poll(poll_msg.id, poll_msg.channel.id, end_timestamp, True)
    @is_owner_or_moderator()
    @poll.command()
    async def delete(self, ctx, message: Optional[Message]):
        """
        delete a poll by providing a message id of a poll message
        """
        if not message:
            converter = ReferenceOrMessage()
            try:
                message = await converter.convert(ctx, message)
            except:
                return await ctx.send("please provide a valid jump url or reply to a poll message")
        poll = await self.fetch_poll(message.id)
        if not poll:
            return await ctx.send("Message was not a poll")
        poll_channel = self.bot.get_channel(poll.get("channel_id"))
        poll_msg = await poll_channel.fetch_message(poll.get("message_id"))
        await poll_msg.delete()
        await self.delete_poll(poll_msg.id)
        await ctx.send("poll deleted")

    
    @poll.command()
    async def when(self, ctx, message: Optional[Message]):
        """
        check how long until a poll is finished by providing the message id of a poll message
        """
        if not message:
            converter = ReferenceOrMessage()
            try:
                message = await converter.convert(ctx, message)
            except:
                return await ctx.send("please provide a valid jump url or reply to a poll message")
        poll = await self.fetch_poll(message.id)
        if not poll:
            return await ctx.send("Message was not a poll")
        end = poll.get("end_ts")
        await ctx.send(str(end - utcnow()))

    def parse_timer(self, timer):
        match = timing_regex.match(timer)
        if not match:
            return None
        if not any(match.groupdict().values()):
            return None
        timer_inputs = match.groupdict()
        for key, value in timer_inputs.items():
            if value is None:
                value = 0
            else:
                value = int(''.join(filter(str.isdigit, value)))
            timer_inputs[key] = value
        delta = timedelta(**timer_inputs)
        return datetime.utcnow() + delta


def setup(bot):
    bot.add_cog(Poll(bot))
