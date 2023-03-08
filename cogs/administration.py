import discord
from discord import app_commands
from discord.enums import ButtonStyle
from discord.ext import commands, tasks
from discord.ext.commands.errors import CommandError
from discord.interactions import Interaction
from discord.utils import TimestampStyle, get
import os.path
import json
from .utils import checks, paginator
from .utils.dataIO import DataIO
from random import choice
import logging
import textwrap
import typing
from io import BytesIO
import asyncio
import re
from fuzzywuzzy import fuzz
from datetime import datetime, timedelta
from collections import Counter

timing_regex = re.compile(r"^(?P<weeks>\d+\s?w(?:eek)?s?)?(?P<days>\d+\s?d(?:ay)?s?)?\s?(?P<hours>\d+\s?h(?:our)?s?)?\s?(?P<minutes>\d+\s?m(?:in(?:ute)?s?)?)?\s?(?P<seconds>\d+\s?s(?:econd)?s?)?")
mention_regex = re.compile('(<@!?)?(\d{17,})>?')

MONTHS_IN_SECONDS = 2629800

class SnowflakeUserConverter(commands.MemberConverter):
    """
    This converter is used for when the user already left the guild to still be able to ban them via
    their Snoflawke/ID
    """
    async def convert(self, ctx, argument):
        try:
            #first try the normal UserConverter (maybe they are in the cache)
            user = await super().convert(ctx, argument)
            return user
        except commands.CommandError:
            #try the cache instead
            pattern = re.compile('(<@!?)?(\d{17,})>?')
            match = pattern.match(argument)
            if match and match.group(2):
                try:
                    return await ctx.bot.fetch_user(int(match.group(2)))
                except (discord.Forbidden, discord.HTTPException):
                    return discord.Object(int(match.group(2)))
            raise commands.BadArgument("Please provide a user mention or a user id when user already left the server")


class DeleteDaysFlag(commands.FlagConverter):
    delete_days: int = commands.flag(name="days", aliases=["dd"], default=0)
    reason : str

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str):
        # This is very scuffed, however this is the best way I have found while not 
        # disrupting the old muscle memory on how the ban command works
        pattern = r"(?:dd|days): \d+"
        match = re.search(pattern, argument)
        if match:
            argument = f"{match.group(0)} reason: {re.sub(pattern, '',argument)}"
        else:
            argument = "reason: " + argument
        return await super().convert(ctx, argument=argument)

class TimeConvertError(CommandError):
    pass

class MuteTimer(commands.Converter):
    
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
        return discord.utils.utcnow() + delta

    async def convert(self, _, argument: str) -> timedelta:
        unmute_ts = self.parse_timer(argument)
        if not unmute_ts: 
            raise TimeConvertError("format was wrong either add quotes around the timer or write it it in this form:\n```\n"
                                  ".remindme 1h20m reminder in 1 hour and 20 minutes\n```")
        diff = unmute_ts - discord.utils.utcnow()
        if diff.total_seconds() > 2 * MONTHS_IN_SECONDS:
            raise TimeConvertError("Please don't mute yourself longer than 2 months, reapply a mute again after time ran out.")
        return diff

class ReportModal(discord.ui.Modal):
    def __init__(self, 
            user: typing.Optional[discord.Member],
            channel: typing.Optional[discord.abc.GuildChannel],
            bot: commands.Bot,
            report_channel: discord.TextChannel
            ):
        self.bot = bot
        self.channel = channel
        self.user = user 
        self.logger = logging.getLogger('report')
        self.report_channel = report_channel
        super().__init__(title="Report Form", timeout=None)

    report = discord.ui.TextInput(label="Report Reason", style=discord.TextStyle.paragraph)
    
    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title="User report", description=self.report)
        user_copy_string = None
        if self.channel:
            embed.add_field(name="Channel", value=self.channel.mention)
        elif interaction.channel:
            embed.add_field(name="Channel", value=interaction.channel.mention)
        if self.user:
            embed.add_field(name="User", value=self.user.mention)
            user_copy_string = f"**{self.user.display_name}** id: {self.user.id} ({self.user.mention})"
            embed.set_thumbnail(url=self.user.display_avatar)
            if last_msg := next(filter(lambda m: m.guild == self.user.guild and m.author == self.user, reversed(self.bot.cached_messages)), None):
                embed.add_field(name="Last Message", value=last_msg.jump_url, inline=False)
        reporter = interaction.user
        self.logger.info('User %s#%s(id:%s) reported: "%s"', reporter.name, reporter.discriminator, reporter.id, self.report)
        await interaction.response.send_message(content="Sent the following report",embed=embed, ephemeral=True)
        await self.report_channel.send(embed=embed, content=user_copy_string)

class ConfirmModal(discord.ui.Modal):
    
    confirm_text = discord.ui.TextInput(label="I confirm", placeholder="write 'mute me' to confirm")
    
    def __init__(self, cog: 'Admin', member: discord.Member, unmute_ts: datetime, *, hide_channels=True, timeout: typing.Optional[float] = None) -> None:
        self.title = "Are you sure?"
        self.member = member
        self.cog = cog
        self.unmute_ts = unmute_ts
        self.hide_channels = hide_channels
        super().__init__(timeout=timeout)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        mute_role = interaction.guild.get_role(await interaction.client.db.fetchval("""
            SELECT role_id FROM mute_roles WHERE guild_id = $1 AND hide_channels = $2
        """, interaction.guild.id, self.hide_channels))
        if self.confirm_text.value.lower() == "mute me":
            await self.cog.add_mute_to_mute_list(member=self.member, timestamp=self.unmute_ts, is_selfmute=True)
            if self.hide_channels:
                await self.cog._store_current_roles(member=self.member)
                try:
                    await self.member.remove_roles(*self.member.roles[1:])
                except discord.Forbidden:
                    pass
            await self.member.add_roles(mute_role)
            await interaction.followup.send("You have been muted, don't bother asking any moderator to unmute you", ephemeral=True)
        else:
            await interaction.followup.send("Confirmation text wrong you have not been muted")

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user != self.member:
            await interaction.response.send_message("You can't interact with this modal", ephemeral=True)
            return False
        return True

class MuteMenu(discord.ui.View):

    def __init__(self, duration: timedelta, *, member: discord.Member, cog: 'Admin', hide_channels=True, timeout: typing.Optional[float] = 180):
        super().__init__(timeout=timeout)
        self.message = None
        self.hide_channels = hide_channels
        self.member = member
        self.duration = duration
        self._admin = cog
        self.toggle_hide.emoji = "\N{WHITE HEAVY CHECK MARK}" if hide_channels else "\N{CROSS MARK}"

    
    async def on_timeout(self) -> None:
        if self.message:
            await self.message.delete()
            self.message = None

    @discord.ui.button(label="Yes", style=ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        unmute_ts = discord.utils.utcnow() + self.duration
        mute_role = interaction.guild.get_role(await interaction.client.db.fetchval("""
            SELECT role_id FROM mute_roles WHERE guild_id = $1 AND hide_channels = $2
        """, interaction.guild.id, self.hide_channels))
        if self.duration.days > 6:
            await interaction.response.send_modal(ConfirmModal(self._admin, self.member, unmute_ts))
        else:
            await interaction.response.defer(ephemeral=True)
            await self._admin.add_mute_to_mute_list(self.member, unmute_ts, is_selfmute=True)
            if self.hide_channels:
                await self._admin._store_current_roles(member=self.member)
                try:
                    await self.member.remove_roles(*self.member.roles[1:])
                except discord.Forbidden:
                    pass
            await self.member.add_roles(mute_role)
            await interaction.followup.send("You have been muted")
        if self.message:
            await self.message.delete()
        self.stop()

    @discord.ui.button(label="No", style=ButtonStyle.red)
    async def deny(self, _: Interaction, __: discord.ui.Button):
        if self.message:
            await self.message.delete()
            self.message = None
        self.stop()

    @discord.ui.button(label="Hide Channels", style=ButtonStyle.blurple)
    async def toggle_hide(self, interaction : discord.Interaction, button: discord.ui.Button):
        self.hide_channels = not self.hide_channels
        button.emoji = "\N{WHITE HEAVY CHECK MARK}" if self.hide_channels else "\N{CROSS MARK}"
        await interaction.response.edit_message(view=self)

    @property
    def embed(self) -> discord.Embed:
        unmute_ts = discord.utils.utcnow() + self.duration
        embed = discord.Embed(title="self mute menu", description=("Are you sure you want to mute for the following duration:"
        f"{discord.utils.format_dt(unmute_ts, 'R')}\n"
        "**BEWARE**: Moderators won't unmute if you change your mind later the selfmute will stay for its entire duration"))
        embed.add_field(name="Hide Channels", value="Click the button to toggle the option to also hide all channels while being muted.")
        return embed

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user != self.member:
            await interaction.response.send_message("You can't interact with this menu", ephemeral=True)
            return False
        return True


class Admin(commands.Cog):
    """Administration commands and anonymous reporting to the moderators"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if os.path.exists('data/report_channel.json'):
            with open('data/report_channel.json') as f:
                json_data = json.load(f)
                self.report_channel = self.bot.get_channel(json_data['channel'])
        else:
            self.report_channel = None
        self.unmute_loop.start()
        if os.path.exists("data/reddit_settings.json"):
            with open("data/reddit_settings.json") as f:
                json_data = json.load(f)
                self.check_channel = self.bot.get_channel(int(json_data["channel"]))
        else:
            self.check_channel = None
        self.units = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}
        self.invocations = []
        self.report_countdown = 60
        self.logger = logging.getLogger('report')
        self.logger.setLevel(logging.INFO)
        self.error_log = logging.getLogger('PoutyBot')
        handler = logging.FileHandler(
            filename='data/reports.log',
            mode="a",
            encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter("%(asctime)s: %(message)s"))
        self.logger.addHandler(handler)
        self.reactions = [
            '\N{WHITE HEAVY CHECK MARK}',
            '\N{NEGATIVE SQUARED CROSS MARK}'
        ]
        self.to_unmute = []

    async def cog_load(self):
        await self.create_mute_database()
        await self.create_voice_unmute_table()
        await self.create_personal_ban_image_db()

    async def get_voice_unmutes(self):
        query =("SELECT * FROM vmutes")
        async with self.bot.db.acquire() as con:
            return await con.fetch(query)

    async def add_to_unmutes(self, member_id):
        query = ("INSERT INTO vmutes VALUES ($1)")
        async with self.bot.db.acquire() as con:
            statement = await con.prepare(query)
            async with con.transaction():
                await statement.fetch(member_id)

    async def remove_from_unmutes(self, member_id):
        query = ("DELETE FROM vmutes WHERE user_id = $1")
        async with self.bot.db.acquire() as con:
            statement = await con.prepare(query)
            async with con.transaction():
                await statement.fetch(member_id)

    async def create_personal_ban_image_db(self):
        query = ("""
        CREATE TABLE IF NOT EXISTS ban_images (
            img_id SERIAL PRIMARY KEY ,
            user_id BIGINT,
            image_link TEXT)
        """)
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await self.bot.db.execute(query)

    async def add_ban_image(self, user_id, link):
        query = """
        INSERT INTO ban_images (user_id, image_link) VALUES ($1, $2)
        """
        async with self.bot.db.acquire() as con:
            statement = await con.prepare(query)
            async with con.transaction():
                return await statement.fetch(user_id, link)

    async def fetch_ban_images(self, user_id):
        query = """
        SELECT img_id, user_id, image_link as link
        FROM ban_images
        WHERE user_id = $1
        """
        async with self.bot.db.acquire() as con:
            statement = await con.prepare(query)
            async with con.transaction():
                return await statement.fetch(user_id)

    async def remove_ban_image(self, user_id, img_id):
        query = """
        DELETE FROM ban_images
        WHERE img_id = $1
        AND user_id = $2
        RETURNING image_link
        """
        async with self.bot.db.acquire() as con:
            statement = await con.prepare(query)
            async with con.transaction():
                return await statement.fetch(img_id, user_id)

    @property
    async def mutes(self):
        query =("SELECT * FROM mutes")
        async with self.bot.db.acquire() as con:
            return await con.fetch(query)

    def cog_unload(self):
        self.unmute_loop.cancel()

    async def create_mute_database(self):
        query = ("CREATE TABLE IF NOT EXISTS mutes ("
                 "user_id BIGINT PRIMARY KEY,"
                 "unmute_ts TIMESTAMP WITH TIME ZONE, "
                 "guild_id BIGINT NOT NULL)")
        query_alter = ("ALTER TABLE mutes ADD COLUMN IF NOT EXISTS selfmute BOOLEAN DEFAULT FALSE")
        mute_role_table = ("CREATE TABLE IF NOT EXISTS mute_roles ("
                "role_id BIGINT PRIMARY KEY, "
                "guild_id BIGINT NOT NULL, "
                "hide_channels BOOLEAN DEFAULT FALSE"
                ")")
        query_role_store = (
                """
                CREATE TABLE IF NOT EXISTS role_store(
                    user_id BIGINT NOT NULL,
                    role_id BIGINT NOT NULL
                )
                """
                )
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await self.bot.db.execute(query)
                await self.bot.db.execute(query_alter)
                await self.bot.db.execute(mute_role_table)
                await self.bot.db.execute(query_role_store)

    async def create_voice_unmute_table(self):
        query = ("CREATE TABLE IF NOT EXISTS vmutes ("
                 "user_id BIGINT PRIMARY KEY)")
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await self.bot.db.execute(query)

    async def send_ban_embed(self, ctx, ban):
        embed = discord.Embed(title=f"{ban.user.name}#{ban.user.discriminator}", description=ban.reason)
        embed.add_field(name="Mention", value=ban.user.mention)
        embed.add_field(name="id", value=ban.user.id)
        embed.set_thumbnail(url=ban.user.display_avatar)
        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def banlist(self, ctx, *, username):
        """search for user in the ban list"""
        bans = [b async for b in ctx.guild.bans()]
        match = mention_regex.match(username)
        if match and match.group(2):
            list_of_matched_entries = list(filter(lambda ban: int(match.group(2)) == ban.user.id, bans))
        else:
            list_of_matched_entries = list(filter(lambda ban: username is None or fuzz.partial_ratio(username.lower(), ban.user.name.lower()) > 80, bans))
        entries = list(map(lambda ban: (f"{ban.user.name}#{ban.user.discriminator}", f"<@!{ban.user.id}>: {ban.reason}"), list_of_matched_entries))
        field_pages = paginator.FieldPages(ctx, entries=entries)
        if len(entries) == 0:
            await ctx.send("banlist search was empty")
        elif len(entries) > 1:
            await field_pages.paginate()
        else:
            ban = list_of_matched_entries[0]
            await self.send_ban_embed(ctx, ban)

    @commands.guild_only()
    @banlist.command(name="reason")
    @commands.has_permissions(ban_members=True)
    async def banlist_reason(self, ctx, *, reason):
        """
        search through the ban list for the reason
        """
        bans = [b async for b in ctx.guild.bans()]
        list_of_matched_entries = list(filter(lambda ban: reason is None or (ban.reason and reason.lower() in ban.reason.lower()), bans))
        entries = list(map(lambda ban: (f"{ban.user.name}#{ban.user.discriminator}", f"<@!{ban.user.id}>: {ban.reason}"), list_of_matched_entries))
        field_pages = paginator.FieldPages(ctx, entries=entries)
        if len(entries) == 0:
            await ctx.send("banlist reason search was empty")
        elif len(entries) > 1:
            await field_pages.paginate()
        else:
            ban = list_of_matched_entries[0]
            await self.send_ban_embed(ctx, ban)


    @commands.group(name="cleanup", invoke_without_command=True)
    @commands.guild_only()
    async def _cleanup(self, ctx: commands.Context, users: commands.Greedy[SnowflakeUserConverter], number: typing.Optional[int] = 10):
        """
        cleanup command that deletes either the last x messages in a channel or the last x messages of one
        or multiple user
        if invoked with username(s), user id(s) or mention(s) then it will delete the user(s) messages:
            `.cleanup test-user1 test-user2 10`
        if invoked with only a number then it will delete the last x messages of a channel:
            `.cleanup 10`
        if invoked by a normal user without manage message permissions will search the last x bot command usages of that user (max 25 messages)
        """
        if not ctx.channel.permissions_for(ctx.author).manage_channels:
            await ctx.invoke(self.mine, search=number)
            return
        if users and ctx.invoked_subcommand is None:
            await ctx.invoke(self.user_, number=number, users=users)
            return
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.channel_, number=number)
            return

    @_cleanup.command(name="me", aliases=["mine"])
    @commands.guild_only()
    async def mine(self, ctx, search=5):
        """
        delete bot messages and your command usages in this channel (up to 25)
        search parameter means this many messages will get searched not deleted
        ignores messages with mentions and reactions
        """
        if search > 25:
            search = 25

        def check(m):
            return (m.author == ctx.me or (m.content.startswith(tuple(ctx.bot.command_prefix) ) and m.author == ctx.author)) and not (m.mentions or m.role_mentions or m.reactions)

        deleted = await ctx.channel.purge(limit=search, check=check, before=ctx.message)
        counts = Counter(m.author.display_name for m in deleted)
        message = [f'{len(deleted)} message{" was" if len(deleted) == 1 else "s were"} removed.' ]
        message.extend(f'- **{author}**: {count}' for author, count in counts.items())
        await ctx.send(content='\n'.join(message), delete_after=10)

    @commands.has_permissions(manage_messages=True)
    @_cleanup.command(name="user")
    @commands.guild_only()
    async def user_(self, ctx, users: commands.Greedy[SnowflakeUserConverter], number=10):
        """
        removes the last x messages of one or multiple users in this channel (defaults to 10)
        """
        number = number if number <= 100 else 100
        if not users:
            await ctx.send("provide at least one user who's messages will be deleted")
            return
        try:
            history_mes = [hist async for hist in ctx.channel.history(limit=100)]
            messages_to_delete = [mes for mes in history_mes if mes.author.id in [u.id for u in users]]
            messages_to_delete = messages_to_delete[:number]
            await ctx.channel.delete_messages(messages_to_delete)
            counts = Counter(m.author.display_name for m in messages_to_delete)
            message = [f'{len(messages_to_delete)} message{" was" if len(messages_to_delete) == 1 else "s were"} removed.' ]
            message.extend(f'- **{author}**: {count}' for author, count in counts.items())
            await ctx.send('\n'.join(message), delete_after=10)
        except (discord.ClientException, discord.HTTPException, discord.Forbidden) as e:
            raise
        except Exception as ex:
            import traceback
            owner = ctx.guild.get_member(self.bot.owner_id)
            if owner:
                await owner.send(traceback.format_exc())
            self.error_log.error(traceback.format_exc())

    @commands.has_permissions(manage_messages=True)
    @_cleanup.command(name="channel")
    @commands.guild_only()
    async def channel_(self, ctx, number=10):
        """
        removes the last x messages from the channel it was called in (defaults to 10)
        """
        number = number if number <= 100 else 100
        question = await ctx.send(f"this will delete the last {number} messages from ALL users. Continue?")
        await question.add_reaction(self.reactions[0])
        await question.add_reaction(self.reactions[1])

        def check_is_author(reaction, user):
            return reaction.message.id == question.id and user.id == ctx.author.id and \
                   reaction.emoji in self.reactions
        try:
            reaction, user = await self.bot.wait_for("reaction_add", check=check_is_author, timeout=20)
            if reaction.emoji == self.reactions[1]:
                await question.delete()
                return
        except asyncio.TimeoutError:
            await question.delete()
            return

        try:
            messages = await ctx.channel.purge(limit=number+1)
            await ctx.send(f"deleted the last {len(messages)-1} messages from this channel", delete_after=5)
        except (discord.ClientException, discord.Forbidden, discord.HTTPException) as e:
            await ctx.send(str(e))
        except Exception as ex:
            import traceback
            owner = ctx.guild.get_member(self.bot.owner_id)
            if owner:
                await owner.send(traceback.print_exc())
            self.error_log.error(traceback.print_exc())



    async def build_message(self, message, report, args):
        embed = discord.Embed(title="**Report Message:**", description=report)
        reported_user = []
        reported_channel = []
        for arg in args:
            if isinstance(arg, discord.User) or isinstance(arg, discord.ClientUser):
                reported_user.append(arg.mention)
            if isinstance(arg, discord.TextChannel):
                reported_channel.append(arg.mention)

        if len(reported_user) > 0:
            embed.add_field(name="**Reported User(s):**", value='\n'.join(reported_user))
        if len(reported_channel) > 0:
            embed.add_field(name="**Reported Channel(s):**", value='\n'.join(reported_channel))
        file_list = []
        file_list_reply = []
        if message.attachments:
            if len(message.attachments) == 1:
                filename = message.attachments[0].filename
                image_bytes = BytesIO(await message.attachments[0].read())
                image_bytes_reply = BytesIO(await message.attachments[0].read())
                f = discord.File(image_bytes, filename=filename)
                f_reply = discord.File(image_bytes_reply, filename=filename)
                embed.set_image(url=f"attachment://{filename}")
                return embed, [f], [f_reply]
            for index, attachment in enumerate(message.attachments):
                image_bytes = BytesIO(await attachment.read())
                image_bytes_reply = BytesIO(await attachment.read())
                file_list.append(discord.File(image_bytes, filename=attachment.filename))
                file_list_reply.append(discord.File(image_bytes_reply, filename=attachment.filename))

        return embed, file_list_reply, file_list

    async def report_checks(self, report, ctx):
        if not report:
            await ctx.author.send("message was missing as a parameter")
            await ctx.author.send(f"```\n\n{ctx.command.usage}\n{ctx.command.help}\n```")
            ctx.command.reset_cooldown(ctx)
            return False
        if not self.report_channel:
            await ctx.send("report channel not set up yet, message a moderator")
            ctx.command.reset_cooldown(ctx)
            return False
        return True

    report = app_commands.Group(name="report", description="Command for reporting users of this server to the moderators")

    @app_commands.checks.cooldown(1,60)
    @report.command(name="user")
    @app_commands.guild_only()
    async def report_user(self, interaction: discord.Interaction,
            channel: typing.Union[discord.TextChannel,discord.VoiceChannel,discord.Thread,None],
            user: typing.Optional[discord.Member]):
        """
        anonymously send a report to the moderators

        Parameters:
        ----------
        report: str
            the report reason
        channel: 
            the channel the report happened in
        user: 
            the user that you are reporting
        """
        await interaction.response.send_modal(ReportModal(user,channel,self.bot, self.report_channel))


    @app_commands.checks.has_any_role("Discord-Senpai", "Admin")
    @app_commands.default_permissions(manage_channels=True)
    @report.command(name="setup")
    async def report_setup(self, interaction: discord.Interaction, channel: typing.Union[discord.TextChannel, discord.Thread]):
        """
        Set the channel where reports go to
        """
        self.report_channel = channel
        with open('data/report_channel.json', 'w') as f:
            json.dump({"channel": self.report_channel.id}, f)
        await interaction.response.send_message(f'{channel.mention} has been set to the report channel')

    @commands.command(name="mban", aliases=["banm"])
    @commands.has_permissions(ban_members=True)
    async def mass_ban(self, ctx: commands.Context, targets: commands.Greedy[discord.Object], *, reason):
        """
        ban multiple users by id (will also clean up their messages)
        format: 
        `mban 12345678 123456 1234567 some reason`
        """
        async with ctx.channel.typing():
            for user in targets:
                try:
                    member = ctx.bot.get_user(user.id)
                    if member:
                        await member.send(textwrap.shorten(f''' You have been banned from the official /r/Animemes discord for the following reason
                    {reason}''', width=2000))
                except discord.Forbidden:
                    continue
                await ctx.guild.ban(user, reason=reason, delete_message_days=1)

            description=f"The following users have been banned for the following reason:\n{reason}\n"
            description += '\n'.join(f'<@{u.id}>' for u in targets)
            embed = discord.Embed(title="Mass ban", description=textwrap.shorten(description, width=4000))
            embed.add_field(name="Message", value=f"[Jump Url]({ctx.message.jump_url})")
            embed.add_field(name="By Moderator", value=ctx.author.mention)
            await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")

        await ctx.send(await self.get_ban_image(ctx.author.id))
        await self.check_channel.send(embed=embed)

    @commands.group(name="ban", usage="ban <User> <reason> `days:|dd:` <number of days>", invoke_without_command=True)
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: typing.Optional[SnowflakeUserConverter], * , reason: DeleteDaysFlag):
        """
        Ban a user from the server with reason.
        This command will try to DM the user with the ban reason, then ban and optionally delete x days of messages if the `days:` or `dd`: flag was given.
        The user can be omitted from the command if it is done in reply to a message, the user who gets replied to will be banned.
        If a user id or user mention is used in the command while replying then the user in the command will be banned **not** the user who got replied to.
        __Examples:__
        `.ban User some valid reason`
        will simply ban a user
        `.ban user some valid reason dd: 1` will ban a user and delete 1 day worth of messages
        """
        if ctx.message.reference and ctx.message.reference.resolved:
            if isinstance(ctx.message.reference.resolved, discord.Message) and member is None:
                member = ctx.message.reference.resolved.author
        if not member:
            return await ctx.send("You need to mention a member to ban or reply to a message to ban the member")
        try:
            if isinstance(member, discord.Member) and 191094827562041345 not in [role.id for role in member.roles]:
                dm_message = "you have been banned for the following reasons:\n{}".format(reason.reason)
                await member.send(dm_message)
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            await ctx.send("couldn't DM reason to user")
        print(reason.delete_days)
        try:
            if isinstance(member, discord.Member):
                if 191094827562041345 in [role.id for role in member.roles]:
                    await ctx.send("I could never ban a dear senpai of mine <a:shinpanic:427749630445486081>")
                    return
                await member.ban(delete_message_days=reason.delete_days, reason=reason.reason[:512])
            else:
                await ctx.guild.ban(user=member, delete_message_days=reason.delete_days, reason=reason.reason[:512])
            mention = member.mention if isinstance(member, discord.Member) else f"<@{member.id}>"
            embed = discord.Embed(title="Ban", description=f"**{mention} banned for the following reason:**\n{reason.reason}")
            if ctx.message.reference and ctx.message.reference.resolved:
                replied = ctx.message.reference.resolved
                if isinstance(replied, discord.Message):
                    embed.add_field(name="In Reply to...", value=f"[{textwrap.shorten(replied.content or '...', 100)}]({replied.jump_url})", inline=False)
            if hasattr(member, 'name'):
                embed.add_field(name="Username", value=member.name)
            embed.add_field(name="User-ID", value=member.id)
            embed.add_field(name="By Moderator", value=ctx.author.mention)
            embed.add_field(name="Ban message", value=f"[jump url]({ctx.message.jump_url})", inline=False)
            await self.check_channel.send(embed=embed)
            await ctx.send(await self.get_ban_image(ctx.author.id))
        except discord.Forbidden:
            await ctx.send("I don't have the permission to ban this user.")
        except discord.HTTPException as httpex:
            await ctx.send(f"HTTP Error {httpex.status}: {httpex.text}")

    @ban.command("cleanup")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def ban_cleanup(self, ctx: commands.Context, member: typing.Union[discord.Member, discord.User], days: int = 1):
        """
        A command for cleaning up an already banned user after they've been banned
        """
        ban = await ctx.guild.fetch_ban(member)
        if not ban:
            return await ctx.send("User hasn't been banned, please use the normal ban command with the `dd` flag.")
        await ctx.guild.unban(member)
        await ctx.guild.ban(member, reason=ban.reason, delete_message_days=days)
        await ctx.message.add_reaction("\N{THUMBS UP SIGN}")


    @commands.group(name="banimg", aliases=["pban", "pb", "set_ban_image"])
    @commands.has_permissions(ban_members=True)
    async def ban_images(self, ctx):
        """
        commands for setting or deleting personalized ban images
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(self.ban_images)

    @ban_images.command(name="add")
    async def ban_images_add(self, ctx, link: typing.Optional[str]):
        """
        add a new personalized ban image
        """
        ban_image_link = link
        if not link and not ctx.message.attachments:
            return await ctx.send("Attach an image to the message or provide a link")
        if not link:
            ban_image_link = ctx.message.attachments[0].url
        await self.add_ban_image(ctx.author.id, ban_image_link)
        await ctx.send("ban image added")

    @ban_images.command(name="list")
    async def ban_images_list(self, ctx):
        """
        list ban images 
        """
        ban_images = await self.fetch_ban_images(ctx.author.id)
        if not ban_images:
            return await ctx.send("No ban images set")

        entries = [(f"id: {img['img_id']}", img['link']) for img in ban_images]
        field_pages = paginator.FieldPages(ctx, entries=entries)
        await field_pages.paginate()

    @ban_images.command(name="remove", aliases=["delete", "del", "rm"])
    async def ban_images_remove(self, ctx, img_id:int):
        """
        remove personalized ban image by providing the database id (use `.banimg list` for finding it)
        """
        remove_img = await self.remove_ban_image(ctx.author.id, img_id)
        if remove_img:
            await ctx.send(f"image with link <{remove_img[0]['image_link']}> removed")
        else:
            await ctx.send("ban image not found")

    async def get_ban_image(self, user_id):
        personal_images = await self.fetch_ban_images(user_id)
        if personal_images:
            return choice([img["link"] for img in personal_images])
        data_io = DataIO()
        ban_images = data_io.load_json("ban_images")
        return choice(ban_images)

    @tasks.loop(seconds=5.0)
    async def unmute_loop(self):
        to_remove = []
        
        try:
            for mute in await self.mutes:
                if mute["unmute_ts"] <= discord.utils.utcnow():
                    try:
                        guild = self.bot.get_guild(mute["guild_id"])
                        member = guild.get_member(mute["user_id"])
                        mute_roles = (discord.Object(r['role_id']) for r in await self.bot.db.fetch("""
                        SELECT role_id FROM mute_roles WHERE guild_id = $1
                        """, guild.id))
                        if member and mute_roles:
                            await member.remove_roles(*mute_roles)
                            stored_roles = await self._get_stored_roles(member)                            
                            stored_roles = [discord.Object(id=s["role_id"]) for s in stored_roles]
                            if stored_roles:
                                await member.add_roles(*stored_roles)
                    except (discord.errors.Forbidden, discord.errors.NotFound) as e:
                        to_remove.append(mute)
                    else:
                        to_remove.append(mute)
            for mute in to_remove:
                await self.remove_user_from_mute_list(mute['user_id'])
        except Exception as e: 
            self.error_log.exception('exception while handling unmutes:')

    async def remove_user_from_mute_list(self, member_id):
        query = ("DELETE FROM mutes "
                 "WHERE user_id = $1"
                 "RETURNING user_id")
        async with self.bot.db.acquire() as con:
            stmt = await con.prepare(query)
            async with con.transaction():
                unmuted_user_id = await stmt.fetchval(member_id)
        return unmuted_user_id

    async def _get_stored_roles(self, member: discord.Member):
        async with self.bot.db.acquire() as con, con.transaction():

            roles = await con.fetch("""
                SELECT role_id FROM role_store 
                WHERE user_id = $1
            """, member.id)
            await con.execute("""
            DELETE FROM role_store WHERE user_id = $1
            """, member.id)
            return roles

    async def _store_current_roles(self, member: discord.Member):
        async with self.bot.db.acquire() as con, con.transaction():
            await con.executemany("""
            INSERT INTO role_store (user_id, role_id) VALUES ($1, $2)
            """, [(member.id, r.id) for r in member.roles[1:]])
        
    async def add_mute_to_mute_list(self, member: discord.Member, timestamp, is_selfmute: bool=False):
        query = ("INSERT INTO mutes "
                 "VALUES ($1,$2, $3, $4) ON CONFLICT(user_id) DO UPDATE SET unmute_ts = $2, selfmute = $3")
        async with self.bot.db.acquire() as con:
            stmt = await con.prepare(query)
            async with con.transaction():
                await stmt.fetch(member.id, timestamp, is_selfmute, member.guild.id)

    async def get_mute_from_list(self, member_id):
        query = ("SELECT * FROM mutes where user_id = $1")
        async with self.bot.db.acquire() as con:
            stmt = await con.prepare(query)
            async with con.transaction():
                return await stmt.fetchrow(member_id)

    def convert_mute_length(self, amount, time_unit):
        if amount == 1 and not time_unit.endswith("s"):
            time_unit = time_unit + "s"

        if time_unit not in self.units.keys():
            return None, "incorrect time unit please choose days, hours, minutes or seconds"
        if amount < 1:
            return None, "amount needs to be at least 1"
        return self.units[time_unit] * amount, None

    @commands.group(invoke_without_command=True)
    async def selfmute(self, ctx, *, timer: MuteTimer):
        """
        selfmute yourself for certain amount of time

        You can't mute yourself more than 2 months, if you need more mute yourself again after the time is up
        """

        mute = await self.get_mute_from_list(ctx.author.id)
        mute_role = ctx.guild.get_role(await self.bot.db.fetchval("""
            SELECT role_id FROM mute_roles WHERE guild_id = $1
        """, ctx.guild.id))
        member = mute_role.guild.get_member(ctx.author.id)
        if mute:
            return await ctx.send("You are already muted")
        if not isinstance(ctx.author, discord.Member):
            ctx.author = mute_role.guild.get_member(ctx.author.id)
        if not ctx.author:
            return await ctx.send("you are not in a guild that has the mute role set up")
        menu = MuteMenu(timer, member=member, cog=self, hide_channels=True)
        msg = await ctx.send(embed=menu.embed, view=menu)
        menu.message = msg

    @selfmute.command()
    @commands.dm_only()
    async def duration(self, ctx):
        """
        show how much time is left of your mutes
        (also works with mod issued mutes).
        """
        mute = await self.get_mute_from_list(ctx.author.id)
        if mute:
            unmute_ts = mute["unmute_ts"]
            return await ctx.send(f"You will unmute {discord.utils.format_dt(unmute_ts, 'R')}")
        await ctx.send("You are not muted.")

    @commands.group(invoke_without_command=True, aliases=["timeout"])
    @commands.has_permissions(manage_roles=True, moderate_members=True)
    async def mute(self, ctx, user: discord.Member, amount: int, time_unit: str, *, reason: typing.Optional[str]):
        """
        mutes the user for a certain amount of time
        usable time codes are days, hours, minutes and seconds
        example:
            .mute @Test-Dummy 5 hours
        """
        length, error_msg = self.convert_mute_length(amount, time_unit)
        mute_role = ctx.guild.get_role(await self.bot.db.fetchval("""
            SELECT role_id FROM mute_roles WHERE guild_id = $1 AND hide_channels = $2
        """, ctx.guild.id, False))

        if not length:
            await ctx.send(error_msg)
            return
        td = timedelta(seconds=length)
        unmute_ts = discord.utils.utcnow() + td
        if td.days > 28:
            await user.add_roles(mute_role)
            await self.add_mute_to_mute_list(user, unmute_ts)
        else:
            await user.edit(timed_out_until=unmute_ts)
        mute_message = f"user {user.mention} was muted ({amount} {time_unit})"
        if reason:
            mute_message = f"{mute_message} for the following reason:\n{reason}"
        await ctx.send(f"{user.mention}\nhttps://tenor.com/view/chazz-yu-gi-oh-shut-up-quiet-anime-gif-16356099")
        await self.check_channel.send(mute_message)

    @commands.has_permissions(manage_roles=True, moderate_members=True)
    @mute.command(name="cancel")
    async def mute_cancel(self, ctx, user:discord.Member):
        """
        cancel a mute
        """
        member = ctx.author
        mute = await self.get_mute_from_list(member.id)
        mute_role = ctx.guild.get_role(await self.bot.db.fetchval("""
            SELECT role_id FROM mute_roles WHERE guild_id = $1 AND hide_channels = $2
        """, ctx.guild.id, False))
        if mute and mute_role:
            await self.remove_user_from_mute_list(member.id)
            guild_member = mute_role.guild.get_member(member.id)
            await guild_member.remove_roles(mute_role)
            return await ctx.send("mute removed")
        else: 
            await user.edit(timed_out_until=None)
            return await ctx.send("user timeout cancelled")


    @checks.is_owner_or_moderator()
    @commands.command(name="vmute")
    async def voice_mute(self, ctx, member: discord.Member, *,reason: typing.Optional[str]):
        """
        mutes a user from voice for the whole server
        """
        await member.edit(mute=True, reason=reason[:512])
        await ctx.send(f"User {member.mention} successfully muted from voice")
        if reason:
            await self.check_channel.send(f"user {member.mention} muted from voice for the following reason:\n"
                                          f"{reason}")

    @checks.is_owner_or_moderator()
    @commands.command(name="vunmute", aliases=["unmute"])
    async def voice_unmute(self, ctx, member: discord.Member, *, reason: typing.Optional[str]):
        """ removes the voice mute from the user"""
        if member.voice and member.voice.mute:
            await member.edit(mute=False, reason=reason[:512])
            await ctx.send(f"User {member.mention} successfully unmuted from voice")
            return
        if member.voice and not member.voice.mute:
            await ctx.send("User is not muted")
            return
        self.to_unmute.append(member.id)
        await self.add_to_unmutes(member.id)
        await ctx.send(f"User {member.mention} added to users that will be unmuted")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not self.to_unmute:
            records = await self.get_voice_unmutes()
            self.to_unmute = [rec["user_id"] for rec in records]
        if member.voice and member.id in self.to_unmute:
            await member.edit(mute=False)
            self.to_unmute.remove(member.id)
            await self.remove_from_unmutes(member.id)


    @checks.is_owner_or_moderator()
    @commands.command(name="setup_mute")
    @commands.guild_only()
    async def mute_setup(self, ctx: commands.Context):
        await ctx.typing()
        mute_roles = await self.bot.db.fetch("SELECT * FROM mute_roles WHERE guild_id = $1", ctx.guild.id)
        if not mute_roles:
            mute_role = await ctx.guild.create_role(name="time-out-zone")
            hide_role = await ctx.guild.create_role(name="channel-hide")
            for category in ctx.guild.categories:
                await category.set_permissions(mute_role, send_messages=False)
                await category.set_permissions(hide_role, view_channel=False)
            await self.bot.db.execute("""
            INSERT INTO mute_roles (role_id, guild_id, hide_channels) VALUES ($1, $3, $4),
            ($2, $3, $5)
            """, mute_role.id, hide_role.id, ctx.guild.id, False, True)
            await ctx.send(f"The roles {mute_role.mention} and {hide_role.mention} have been created")


    @checks.is_owner_or_moderator()
    @commands.hybrid_group(name="channel", with_app_command=True)
    async def channel_group(self, ctx):
        pass

    @checks.is_owner_or_moderator()
    @channel_group.command(name="rename")
    @app_commands.rename(new_name="name")
    @app_commands.describe(new_name="the new name of the channel")
    @app_commands.describe(channel="the channel to rename")
    async def channel_rename(self, ctx: commands.Context, channel: discord.TextChannel, *,new_name: str):
        """
        rename a channel via bot command which allows spaces and default emoji
        """
        async with ctx.typing(ephemeral=True):
            await channel.edit(name=new_name)
            if ctx.interaction:
                await ctx.send("\N{WHITE HEAVY CHECK MARK}", ephemeral=True)
            else:
                await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")

    @checks.is_owner_or_moderator()
    @commands.guild_only()
    @channel_group.command(name="create")
    @app_commands.describe(category="under what category to put the new channel")
    async def channel_create(self, ctx: commands.Context, category: typing.Optional[discord.CategoryChannel], * , name: str):
        """
        create a channel via bot command which allows spaces and default emoji
        """
        overwrites = {
                    ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
                    ctx.author: discord.PermissionOverwrite(read_messages=True)
                }
        async with ctx.typing(ephemeral=True):
            await ctx.guild.create_text_channel(name=name, category=category, overwrites=overwrites)
            if ctx.interaction:
                await ctx.send("\N{WHITE HEAVY CHECK MARK}", ephemeral=True)
            else:
                await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")
    @commands.Cog.listener()
    async def on_member_join(self, member):
        muted_user_ids = [m['user_id'] for m in await self.mutes]
        mute_role = member.guild.get_role(await self.bot.db.fetchval("""
            SELECT role_id FROM mute_roles WHERE guild_id = $1 AND hide_channels = $2
        """, member.guild.id, False))
        if member.id in muted_user_ids:
            await member.add_roles(mute_role)
            await self.check_channel.send(f"{member.mention} tried to circumvent a mute by leaving")
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        muted_user_ids = [m['user_id'] for m in await self.mutes]
        if member.id in muted_user_ids:
            await self.check_channel.send(f"{member.mention} left the server while being muted")


async def setup(bot):
    await bot.add_cog(Admin(bot))
