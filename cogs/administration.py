import discord
from discord.ext import commands, tasks
from discord.utils import get
import os.path
import json
from .utils import checks, paginator
from .utils.dataIO import DataIO
from random import choice
import logging
import typing
from io import BytesIO
import asyncio
import re
import datetime


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
                return discord.Object(int(match.group(2)))
            raise commands.BadArgument("Please provide a user mention or a user id when user already left the server")


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
        if os.path.exists('data/mute_list.json'):
            with open('data/mute_list.json') as f:
                json_data = json.load(f)
                for server in self.bot.guilds:
                    self.mute_role = get(server.roles, id=int(json_data['mute_role']))
                    if self.mute_role is not None:
                        break
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
        self.bot.loop.create_task(self.create_mute_database())
        self.bot.loop.create_task(self.create_voice_unmute_table())
        self.to_unmute = []

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
                 "unmute_ts TIMESTAMP )")
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await self.bot.db.execute(query)

    async def create_voice_unmute_table(self):
        query = ("CREATE TABLE IF NOT EXISTS vmutes ("
                 "user_id BIGINT PRIMARY KEY)")
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await self.bot.db.execute(query)


    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def banlist(self, ctx, *, username=None):
        """search for user in the ban list"""
        bans = await ctx.guild.bans()
        list_of_matched_users = []
        for ban in bans:
            if username is None or username.lower() in ban.user.name.lower():
                list_of_matched_users.append(ban)

        entries = []
        for ban in list_of_matched_users:
            entries.append((f"{ban.user.name}#{ban.user.discriminator}", f"<@!{ban.user.id}>: {ban.reason}"))
        text_pages = paginator.FieldPages(ctx, entries=entries)
        await text_pages.paginate()

    @commands.has_permissions(manage_messages=True)
    @commands.group(name="cleanup")
    async def _cleanup(self, ctx, users: commands.Greedy[SnowflakeUserConverter], number: typing.Optional[int] = 10):
        """
        cleanup command that deletes either the last x messages in a channel or the last x messages of one
        or multiple user
        if invoked with username(s), user id(s) or mention(s) then it will delete the user(s) messages:
            .cleanup test-user1 test-user2 10
        if invoked with only a number then it will delete the last x messages of a channel:
            .cleanup 10
        """
        if users and ctx.invoked_subcommand is None:
            await ctx.invoke(self.user_, number=number, users=users)
            return
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.channel_, number=number)
            return

    @_cleanup.command(name="user")
    async def user_(self, ctx, users: commands.Greedy[SnowflakeUserConverter], number=10):
        """
        removes the last x messages of one or multiple users in this channel (defaults to 10)
        """
        number = number if number <= 100 else 100
        if not users:
            await ctx.send("provide at least one user who's messages will be deleted")
            return
        try:
            history_mes = await ctx.channel.history(limit=100).flatten()
            messages_to_delete = [mes for mes in history_mes if mes.author.id in [u.id for u in users]]
            await ctx.channel.delete_messages(messages_to_delete[:number])
            await ctx.send(f"deleted {len(messages_to_delete[0:number])} messages")
        except (discord.ClientException, discord.HTTPException, discord.Forbidden) as e:
            raise
        except Exception as ex:
            import traceback
            owner = ctx.guild.get_member(self.bot.owner_id)
            if owner:
                await owner.send(traceback.format_exc())
            self.error_log.error(traceback.format_exc())

    @_cleanup.command(name="channel")
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
            await ctx.send(f"deleted the last {len(messages)-1} messages from this channel")
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

    @commands.cooldown(rate=1, per=60, type=commands.BucketType.user)
    @commands.group(usage=f'"report message" "Username With Space" 13142313324232 general-channel [...]')
    @commands.dm_only()
    async def report(self, ctx: commands.Context, report: typing.Optional[str], args: commands.Greedy[typing.Union[discord.User, discord.TextChannel]]):
        """
        anonymously report a user to the moderators
        usage:
        ONLY WORKS IN PRIVATE MESSAGES TO THE BOT!
        !report "report reason" reported_user [name/id] (optional) channel_id [name/id] (optional)

        don't forget the quotes around the reason, optionally you can attach a screenshot via file upload

        examples:
        !report "I was meanly bullied by <user>" 123456789 0987654321
        !report "I was bullied by <user>"
        !report "I was bullied by <user>" User_Name general
        """
        author = ctx.message.author
        if report == 'setup':
            if checks.is_owner_or_moderator_check(ctx.message):
                await ctx.invoke(self.setup)
                return
            else:
                await ctx.send("You don't have permission to do this")
                ctx.command.reset_cooldown(ctx)
                return
        if not await self.report_checks(report, ctx):
            return
        embed, file_list_reply, file_list = await self.build_message(ctx.message, report, args)
        user_copy = await ctx.author.send(f"going to send the following report message:"
                                          f"\n check with {self.reactions[0]} to send"
                                          f" or {self.reactions[1]} to abort",
                                          files=file_list_reply, embed=embed)
        for reaction in self.reactions:
            await user_copy.add_reaction(reaction)

        def react_check(reaction, user):
            if user is None or user.id != ctx.author.id:
                return False
            if reaction.message.id != user_copy.id:
                return False
            if reaction.emoji in self.reactions:
                return True
            return False
        try:
            reaction, user = await self.bot.wait_for('reaction_add', check=react_check, timeout=60)
        except asyncio.TimeoutError as tm:
            await user_copy.edit(content="You waited too long, use the command again to send a report")
            await user_copy.remove_reaction(self.reactions[0], self.bot.user)
            await user_copy.remove_reaction(self.reactions[1], self.bot.user)
            ctx.command.reset_cooldown(ctx)
            return
        else:
            if reaction.emoji == self.reactions[0]:
                await self.report_channel.send(embed=embed, files=file_list)
                self.logger.info('User %s#%s(id:%s) reported: "%s"', author.name, author.discriminator, author.id, report)
                await author.send("successfully sent")
            else:
                await user_copy.delete()
                ctx.command.reset_cooldown(ctx)


    @report.command(name="setup")
    @commands.has_any_role("Discord-Senpai", "Admin")
    async def setup(self, ctx):
        """
        use '[.,!]report setup' in the channel that should become the report channel
        """
        self.report_channel = ctx.message.channel
        with open('data/report_channel.json', 'w') as f:
            json.dump({"channel": self.report_channel.id}, f)
        await ctx.send('This channel is now the report channel')

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: SnowflakeUserConverter, *, reason: str):
        try:
            if isinstance(member, discord.Member) and 191094827562041345 not in [role.id for role in member.roles]:
                dm_message = "you have been banned for the following reasons:\n{}".format(reason)
                await member.send(dm_message)
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            await ctx.send("couldn't DM reason to user")
        try:
            if isinstance(member, discord.Member):
                if 191094827562041345 in [role.id for role in member.roles]:
                    await ctx.send("I could never ban a dear senpai of mine <a:shinpanic:427749630445486081>")
                    return
                await member.ban(delete_message_days=0, reason=reason[:512])
            else:
                await ctx.guild.ban(user=member, delete_message_days=0, reason=reason[:512])
            mention = member.mention if isinstance(member, discord.Member) else f"<@{member.id}>"
            message = "banned {} for the following reason:\n{}".format(mention, reason)
            await self.check_channel.send(message)
            await ctx.send(self.get_ban_image())
        except discord.Forbidden:
            await ctx.send("I don't have the permission to ban this user.")
        except discord.HTTPException as httpex:
            await ctx.send(f"HTTP Error {httpex.status}: {httpex.text}")

    def get_ban_image(self):
        data_io = DataIO()
        ban_images = data_io.load_json("ban_images")
        return choice(ban_images)

    @tasks.loop(seconds=5.0)
    async def unmute_loop(self):
        to_remove = []
        try:
            for mute in await self.mutes:
                if mute["unmute_ts"] <= datetime.datetime.utcnow():
                    try:
                        user = get(self.mute_role.guild.members, id=mute["user_id"])
                        if user:
                            await user.remove_roles(self.mute_role)
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
    async def add_mute_to_mute_list(self, member_id, timestamp):
        query = ("INSERT INTO mutes "
                 "VALUES ($1,$2) ON CONFLICT(user_id) DO UPDATE SET unmute_ts = $2")
        async with self.bot.db.acquire() as con:
            stmt = await con.prepare(query)
            async with con.transaction():
                await stmt.fetch(member_id, timestamp)

    def convert_mute_length(self, amount, time_unit):
        if amount == 1 and not time_unit.endswith("s"):
            time_unit = time_unit + "s"

        if time_unit not in self.units.keys():
            return None, "incorrect time unit please choose days, hours, minutes or seconds"
        if amount < 1:
            return None, "amount needs to be at least 1"
        return self.units[time_unit] * amount, None

    @commands.command()
    async def selfmute(self, ctx, amount:int, time_unit:str):
        """
        selfmute yourself for certain amount of time
        """

        length, error_msg = self.convert_mute_length(amount, time_unit)
        if not length:
            await ctx.send(error_msg)
            return
        if length > 7 * self.units["days"]:
            question = await ctx.send(f"Are you sure you want to be muted for {(length/self.units['days']):.2f} days?\n"
                                      f"answer with  Y[es] or N[o]")

            def msg_check(message):
                return message.author.id == ctx.author.id and message.channel.id == ctx.message.channel.id
            try:
                message = await self.bot.wait_for("message", check=msg_check, timeout=20.0)
                if re.match(r"y(es)?", message.content.lower()):
                    pass
                else:
                    await question.edit(content="self mute aborted")
                    return
            except asyncio.TimeoutError:
                await question.edit(content="Timeout: mute aborted")
                return

        unmute_ts = datetime.datetime.utcnow() + datetime.timedelta(seconds=length)
        await ctx.author.add_roles(self.mute_role)
        await ctx.send("You have been muted")
        await self.add_mute_to_mute_list(ctx.author.id, unmute_ts)


    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, user: discord.Member, amount: int, time_unit: str, *, reason: typing.Optional[str]):
        """
        mutes the user for a certain amount of time
        usable time codes are days, hours, minutes and seconds
        example:
            .mute @Test-Dummy 5 hours
        """
        length, error_msg = self.convert_mute_length(amount, time_unit)
        if not length:
            await ctx.send(error_msg)
            return
        unmute_ts = datetime.datetime.utcnow() + datetime.timedelta(seconds=length)
        mute_message = f"user {user.mention} was muted"
        await user.add_roles(self.mute_role)
        await ctx.send(mute_message)
        if reason:
            mute_message = f"{mute_message} for the following reason:\n{reason}"
        await self.add_mute_to_mute_list(user.id, unmute_ts)
        await self.check_channel.send(mute_message)

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
    @commands.command(name="setup_mute", pass_context=True)
    async def mute_setup(self, ctx, role):
        mute_role = get(ctx.message.guild.roles, name=role)
        self.mute_role = mute_role

    @commands.Cog.listener()
    async def on_member_join(self, member):
        muted_user_ids = [m['user_id'] for m in await self.mutes]
        if member.id in muted_user_ids:
            await member.add_roles(self.mute_role)
            await self.check_channel.send(f"{member.mention} tried to circumvent a mute by leaving")
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        muted_user_ids = [m['user_id'] for m in await self.mutes]
        if member.id in muted_user_ids:
            await self.check_channel.send(f"{member.mention} left the server while being muted")


def setup(bot):
    bot.add_cog(Admin(bot))
