import discord
from discord.ext import commands, tasks
from discord.utils import get
import os.path
import json
from .utils import checks
from .utils.dataIO import DataIO
import time
from random import choice
import logging
import typing
from io import BytesIO
import asyncio


class UserOrChannel(commands.Converter):
    async def convert(self, ctx, argument):
        user_converter = commands.UserConverter()
        channel_converter = commands.TextChannelConverter()
        try:
            found_member = await user_converter.convert(ctx, argument)
            return found_member
        except commands.BadArgument:
            try:
                found_channel = await channel_converter.convert(ctx, argument)
                return found_channel
            except commands.BadArgument:
                raise commands.BadArgument("Didn't find Member or Channel with name {}.".format(argument))


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
                self.mutes = json_data['mutes']
                for server in self.bot.guilds:
                    self.mute_role = get(server.roles, id=int(json_data['mute_role']))
                    if self.mute_role is not None:
                        break
            self.unmute_loop.start()
        else:
            self.mutes = []
            self.mute_role = None
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

    def cog_unload(self):
        self.unmute_loop.cancel()
        self.save_mute_list()

    def save_mute_list(self):
        data = {
            "mute_role": self.mute_role.id,
            "mutes": self.mutes
        }
        with open("data/mute_list.json", 'w') as f:
            json.dump(data, f)

    @commands.has_permissions(manage_messages=True)
    @commands.group(name="cleanup")
    async def _cleanup(self, ctx, users: commands.Greedy[discord.Member], number: typing.Optional[int] = 10):
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
    async def user_(self, ctx, users: commands.Greedy[discord.Member], number=10):
        """
        removes the last x messages of one or multiple users in this channel (defaults to 10)
        """
        number = number if number <= 100 else 100
        channel = ctx.channel
        if not users:
            await ctx.send("provide at least one user who's messages will be deleted")
        try:
            messages = await channel.history(limit=500, before=ctx.message).flatten()
            user_messages = [mes for mes in messages if mes.author in users]
            await channel.delete_messages(user_messages[0:number])
            user_names = [user.display_name for user in users]
            await ctx.send(f"deleted the last {len(user_messages[0:number])} messages by {', '.join(user_names)}")
        except (discord.ClientException, discord.HTTPException, discord.Forbidden) as e:
            await ctx.send(str(e))

    @_cleanup.command(name="channel")
    async def channel_(self, ctx, number=10):
        """
        removes the last x messages from the channel it was called in (defaults to 10)
        """
        number = number if number <= 100 else 100
        messages = await ctx.channel.history(limit=number, before=ctx.message).flatten()
        try:
            await ctx.channel.delete_messages(messages)
            await ctx.send(f"deleted the last {len(messages)} messages from this channel")
        except (discord.ClientException, discord.Forbidden, discord.HTTPException) as e:
            await ctx.send(str(e))


    async def build_message(self, message, report, args):
        report_message = "**Report Message:**\n```{}```\n\n".format(report)
        reported_user = []
        reported_channel = []
        for arg in args:
            if isinstance(arg, discord.User) or isinstance(arg, discord.ClientUser):
                reported_user.append(arg.mention)
            if isinstance(arg, discord.TextChannel):
                reported_channel.append(arg.mention)

        if len(reported_user) > 0:
            report_message += "**Reported User(s):**\n{}\n".format(", ".join(reported_user))
        if len(reported_channel) > 0:
            report_message += "**In Channel(s):**\n{}\n".format(", ".join(reported_channel))
        file_list = []
        file_list_reply = []
        if message.attachments:
            for attachment in message.attachments:
                image_bytes = BytesIO(await attachment.read())
                image_bytes_reply = BytesIO(await attachment.read())
                file_list.append(discord.File(image_bytes, filename=attachment.filename))
                file_list_reply.append(discord.File(image_bytes_reply, filename=attachment.filename))
            report_message += "**Included Screenshot:**"

        return report_message, file_list_reply, file_list

    async def report_checks(self, report, ctx):
        if not report:
            await ctx.author.send("message was missing as a parameter")
            await ctx.author.send(f"```\n\n{ctx.command.usage}\n{ctx.command.help}\n```")
            ctx.command.reset_cooldown(ctx)
            return False
        if type(ctx.message.channel) is not discord.DMChannel:
            await ctx.author.send("Only use the `report` command in private messages")
            await ctx.send("Only use the `report` command in private messages")
            ctx.command.reset_cooldown(ctx)
            return False
        if not self.report_channel:
            await ctx.send("report channel not set up yet, message a moderator")
            ctx.command.reset_cooldown(ctx)
            return False
        return True

    @commands.cooldown(rate=1, per=60, type=commands.BucketType.user)
    @commands.group(usage=f'"report message" "Username With Space" 13142313324232 general-channel [...]')
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
        report_message, file_list_reply, file_list = await self.build_message(ctx.message, report, args)
        user_copy = await ctx.author.send(f"going to send the following report message:"
                                          f"\n{report_message}\n check with {self.reactions[0]} to send"
                                          f" or {self.reactions[1]} to abort",
                                          files=file_list_reply)
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
                await self.report_channel.send(report_message, files=file_list)
                self.logger.info('User %s#%s(id:%s) reported: "%s"', author.name, author.discriminator, author.id, report)
                await author.send("successfully sent")
            else:
                await user_copy.edit(content="report cancelled")
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

    @commands.command(name="ban", pass_context=True)
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str):
        try:
            dm_message = "you have been banned for the following reasons:\n{}".format(reason)
            await member.send(dm_message)
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            await ctx.send("couldn't DM reason to user")
        try:
            await member.ban(delete_message_days=0, reason=reason)
            message = "banned {} for the following reason:\n{}".format(member.mention, reason)
            await self.check_channel.send(message)
            await ctx.send(self.get_ban_image())
        except discord.Forbidden:
            await ctx.send("I don't have the permission to ban this user.")
        except discord.HTTPException:
            await ctx.send("There was a HTTP or connection issue ban failed")

    def get_ban_image(self):
        data_io = DataIO()
        ban_images = data_io.load_json("ban_images")
        return choice(ban_images)

    @tasks.loop(seconds=5.0)
    async def unmute_loop(self):
        to_remove = []
        for mute in self.mutes:
            if mute["unmute_ts"] <= int(time.time()):
                try:
                    user = get(self.mute_role.guild.members, id=mute["user"])
                    if user:
                        await user.remove_roles(self.mute_role)
                except (discord.errors.Forbidden, discord.errors.NotFound):
                    to_remove.append(mute)
                except discord.errors.HTTPException:
                    pass
                else:
                    to_remove.append(mute)
        for mute in to_remove:
            self.mutes.remove(mute)
            if self.check_channel is not None:
                user = get(self.mute_role.guild.members, id=mute["user"])
                if user:
                    await self.check_channel.send("User {0} unmuted".format(user.mention))
        if to_remove:
            self.save_mute_list()

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, user: discord.Member, amount: int, time_unit: str):
        """
        mutes the user for a certain amount of time
        usable time codes are days, hours, minutes and seconds
        example:
            .mute @Test-Dummy 5 hours
        """
        if amount == 1 and not time_unit.endswith("s"):
            time_unit = time_unit + "s"
        if time_unit not in self.units.keys():
            await ctx.send("incorrect time unit please choose days, hours, minutes or seconds")
            return
        if amount < 1:
            await ctx.send("amount needs to be at least 1")
            return
        length = self.units[time_unit] * amount
        unmute_ts = int(time.time() + length)
        await user.add_roles(self.mute_role)
        await ctx.send("user {0} was muted".format(user.mention))
        self.mutes.append({"user": user.id, "unmute_ts": unmute_ts})
        self.save_mute_list()

    @checks.is_owner_or_moderator()
    @commands.command(name="setup_mute", pass_context=True)
    async def mute_setup(self, ctx, role):
        mute_role = get(ctx.message.guild.roles, name=role)
        self.mute_role = mute_role
        self.save_mute_list()


def setup(bot):
    bot.add_cog(Admin(bot))
