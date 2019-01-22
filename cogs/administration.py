import discord
from discord.ext import commands
import os.path
import json
from .utils import checks
import time
import logging



class UserOrChannel(commands.Converter):
    async def convert(self):
        user_converter = commands.UserConverter(ctx=self.ctx, argument=self.argument)
        channel_converter = commands.ChannelConverter(ctx=self.ctx, argument=self.argument)
        try:
            found_member = user_converter.convert()
            return found_member
        except commands.BadArgument:
            try:
                found_channel = channel_converter.convert()
                return found_channel
            except commands.BadArgument:
                raise commands.BadArgument("Didn't find Member or Channel with name {}.".format(self.argument))


class Admin:
    def __init__(self, bot):
        self.bot = bot
        if os.path.exists('data/report_channel.json'):
            with open('data/report_channel.json') as f:
                json_data = json.load(f)
                self.report_channel = self.bot.get_channel(json_data['channel'])
        else:
            self.report_channel = None
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


    @commands.group(pass_context=True)
    async def report(self, ctx, message: str, *args: UserOrChannel):
        """
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
        if message == 'setup':
            if checks.is_owner_or_moderator_check(ctx.message):
                await ctx.invoke(self.setup, ctx=ctx)
                return
            else:
                await self.bot.say("You don't have permission to do this")
                return
        if ctx.message.channel.type is not discord.ChannelType.private:
            await self.bot.whisper("Only use the `report` command in private messages")
            await self.bot.say("Only use the `report` command in private messages")
            return
        if not self.report_channel:
            await self.bot.say("report channel not set up yet, message a moderator")
            return
        if author.id not in [i['user'] for i in self.invocations]:
            invocation = {"user": ctx.message.author.id, "timestamp": time.time()}
            self.invocations.append(invocation)
        else:
            last_invocation = [i['timestamp'] for i in self.invocations if author.id == i['user']]
            time_diff = int(time.time() - last_invocation[0])
            if time_diff < self.report_countdown:
                await self.bot.whisper("Too early to report again wait for another {} seconds"
                                       .format(self.report_countdown - time_diff))
                return
            else:
                invocation = {"user": ctx.message.author.id, "timestamp": time.time()}
                self.invocations.remove([i for i in self.invocations if author.id == i['user']][0])
                self.invocations.append(invocation)

        report_message = "**Report Message:**\n```{}```\n\n".format(message)
        reported_user = []
        reported_channel = []
        for arg in args:
            if isinstance(arg, discord.User):
                reported_user.append(arg.mention)
            if isinstance(arg, discord.Channel):
                reported_channel.append(arg.mention)

        if len(reported_user) > 0:
            report_message += "**Reported User(s):**\n{}\n".format(", ".join(reported_user))
        if len(reported_channel) > 0:
            report_message += "**In Channel(s):**\n{}\n".format(", ".join(reported_channel))
        if ctx.message.attachments:
            report_message += "**Included Screenshot:**\n{}\n".format(ctx.message.attachments[0]['url'])

        await self.bot.send_message(self.report_channel, report_message)
        self.logger.info('User %s#%s(id:%s) reported: "%s"', author.name, author.discriminator, author.id, message)
        await self.bot.whisper("report successfully sent.")


    @report.command(name="setup")
    @checks.is_owner_or_moderator()
    async def setup(self, ctx):
        """
        use '[.,!]report setup' in the channel that should become the report channel
        """
        self.report_channel = ctx.message.channel
        with open('data/report_channel.json' , 'w') as f:
            json.dump({"channel" : self.report_channel.id}, f)
        await self.bot.say('This channel is now the report channel')

    @commands.command(name="ban", pass_context=True)
    @checks.is_owner_or_moderator()
    async def ban(self, ctx, member: discord.Member, *, reason:str):
        try:
            await self.bot.send_message(member, content=reason)
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            await self.bot.say("couldn't DM reason to user")
        try:
            await self.bot.ban(member, delete_message_days=0)
            await self.bot.say("https://i.imgur.com/BdUCfLb.png")
        except discord.Forbidden:
            await self.bot.say("I don't have the permission to ban this user.")
        except discord.HTTPException:
            await self.bot.say("There was a HTTP or connection issue ban failed")


def setup(bot):
    bot.add_cog(Admin(bot))
