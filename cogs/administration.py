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
from fuzzywuzzy import fuzz
from datetime import datetime, timedelta

timing_regex = re.compile(r"^(?P<days>\d+\s?d(?:ay)?s?)?\s?(?P<hours>\d+\s?h(?:our)?s?)?\s?(?P<minutes>\d+\s?m(?:in(?:ute)?s?)?)?\s?(?P<seconds>\d+\s?s(?:econd)?s?)?")

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
        self.bot.loop.create_task(self.create_personal_ban_image_db())
        self.to_unmute = []

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
                 "unmute_ts TIMESTAMP )")
        query_alter = ("ALTER TABLE mutes ADD COLUMN IF NOT EXISTS selfmute BOOLEAN DEFAULT FALSE")
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await self.bot.db.execute(query)
                await self.bot.db.execute(query_alter)

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
        embed.set_thumbnail(url=ban.user.avatar_url)
        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def banlist(self, ctx, *, username=None):
        """search for user in the ban list"""
        bans = await ctx.guild.bans()
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
        bans = await ctx.guild.bans()
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
    async def ban(self, ctx, member: SnowflakeUserConverter, delete_message_days: typing.Optional[int] = 0, *, reason: str):
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
                await member.ban(delete_message_days=delete_message_days, reason=reason[:512])
            else:
                await ctx.guild.ban(user=member, delete_message_days=0, reason=reason[:512])
            mention = member.mention if isinstance(member, discord.Member) else f"<@{member.id}>"
            embed = discord.Embed(title="Ban", description=f"**{mention} banned for the following reason:**\n{reason}")
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
                if mute["unmute_ts"] <= datetime.utcnow():
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

    async def add_mute_to_mute_list(self, member_id, timestamp, is_selfmute: bool=False):
        query = ("INSERT INTO mutes "
                 "VALUES ($1,$2, $3) ON CONFLICT(user_id) DO UPDATE SET unmute_ts = $2, selfmute = $3")
        async with self.bot.db.acquire() as con:
            stmt = await con.prepare(query)
            async with con.transaction():
                await stmt.fetch(member_id, timestamp, is_selfmute)

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
    async def selfmute(self, ctx, *, timer):
        """
        selfmute yourself for certain amount of time
        """

        mute = await self.get_mute_from_list(ctx.author.id)
        unmute_ts = self.parse_timer(timer)
        if not unmute_ts: 
            return await ctx.send("format was wrong either add quotes around the timer or write it it in this form:\n```\n"
                                  ".remindme 1h20m reminder in 1 hour and 20 minutes\n```")
        difference = unmute_ts - datetime.utcnow()
        if mute:
            return await ctx.send("You are already muted use `.selfmute cancel` to cancel a selfmute")
        if not isinstance(ctx.author, discord.Member):
            ctx.author = self.mute_role.guild.get_member(ctx.author.id)
        if not ctx.author:
            return await ctx.send("you are not in a guild that has the mute role set up")
        if difference.days > 6:
            question = await ctx.send(f"Are you sure you want to be muted for {difference}?\n"
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

        await ctx.author.add_roles(self.mute_role)
        await ctx.send("You have been muted")
        await self.add_mute_to_mute_list(ctx.author.id, unmute_ts, True)

    @selfmute.command()
    @commands.dm_only()
    async def cancel(self, ctx):
        """
        cancel a selfmute
        """
        member = ctx.author
        mute = await self.get_mute_from_list(member.id)
        if mute and mute["selfmute"]:
            await self.remove_user_from_mute_list(member.id)
            guild_member = self.mute_role.guild.get_member(member.id)
            await guild_member.remove_roles(self.mute_role)
            return await ctx.send("selfmute removed")
        await ctx.send("You are either not muted or your mute is not a selfmute")

    @selfmute.command()
    @commands.dm_only()
    async def duration(self, ctx):
        """
        show how much time is left of your mutes
        (also works with mod issued mutes).
        """
        mute = await self.get_mute_from_list(ctx.author.id)
        if mute:
            time_diff = mute["unmute_ts"] - datetime.utcnow()
            days = f"{time_diff.days} days " if time_diff.days else ""
            hours, remainder = divmod(time_diff.seconds, 3600)
            minutes, remainder = divmod(remainder, 60)
            seconds = int(remainder)
            return await ctx.send(f"Your mute will last for {days}"
                                  f"{hours}h {minutes}min {seconds}s.")
        
        await ctx.send("You are not muted.")

    @commands.group(invoke_without_command=True)
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
        unmute_ts = datetime.utcnow() + timedelta(seconds=length)
        mute_message = f"user {user.mention} was muted ({amount} {time_unit})"
        await user.add_roles(self.mute_role)
        await ctx.send(f"{user.mention}\nhttps://tenor.com/view/chazz-yu-gi-oh-shut-up-quiet-anime-gif-16356099")
        if reason:
            mute_message = f"{mute_message} for the following reason:\n{reason}"
        await self.add_mute_to_mute_list(user.id, unmute_ts)
        await self.check_channel.send(mute_message)

    @commands.has_permissions(manage_roles=True)
    @mute.command(name="cancel")
    async def mute_cancel(self, ctx, user:discord.Member):
        """
        cancel a mute
        """
        member = ctx.author
        mute = await self.get_mute_from_list(member.id)
        if mute:
            await self.remove_user_from_mute_list(member.id)
            guild_member = self.mute_role.guild.get_member(member.id)
            await guild_member.remove_roles(self.mute_role)
            return await ctx.send("mute removed")
        await ctx.send("User is not muted right now or at least is not in the database")


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
