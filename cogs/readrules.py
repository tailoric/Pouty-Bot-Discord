from discord.ext import commands, tasks
from discord.utils import get
import discord
import json
import datetime
import logging
import traceback
from random import choice
import re
import asyncio
from .utils.dataIO import DataIO
from .utils.checks import is_owner_or_moderator
from cogs.default import CustomHelpCommand
from io import TextIOWrapper, BytesIO

class JumpMessageView(discord.ui.View):
    def __init__(self, message: discord.Message):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(url=message.jump_url, label='Scroll Up', emoji="\N{UPWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}", style=discord.ButtonStyle.primary))
        self.add_item(discord.ui.Button(
            url="https://discord.com/channels/187423852224053248/366659034410909717/",
            label="confirm you read the rules",
            emoji="\N{OPEN BOOK}"
            ))
         

class AnimemesHelpFormat(CustomHelpCommand):


    def random_response(self):
        with open("data/rules_channel_phrases.json")as f:
            phrases = json.load(f)
            return choice(phrases["help"])


    async def send_bot_help(self, mapping):
        channel = self.context.channel
        if channel and channel.id == 366659034410909717:
            await self.context.send(self.random_response())
            return
        await super().send_bot_help(mapping)


class ReadRules(commands.Cog):
    """
    Animemes focused cog
    """
    async def init_database(self):
        query = '''
                CREATE TABLE IF NOT EXISTS new_memesters(
                    user_id BIGINT,
                    time_over timestamp

                );
                '''
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute(query)
    async def add_new_memester(self, new_user):
        query = '''
            INSERT INTO new_memesters VALUES ($1, $2) ON CONFLICT DO NOTHING 
        '''
        async with self.bot.db.acquire() as con:
            statement = await con.prepare(query)
            time_over = datetime.datetime.utcnow() + datetime.timedelta(weeks=1)
            async with con.transaction():
                await statement.fetch(new_user.id, time_over)

    async def fetch_new_memesters(self):
        query = '''
            SELECT * FROM new_memesters
        '''
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                return await con.fetch(query)
    async def remove_user_from_new_list(self, user_id):
        query = '''
            DELETE FROM new_memesters WHERE user_id = $1
        '''
        async with self.bot.db.acquire() as con:
            statement = await con.prepare(query)
            async with con.transaction():
                await statement.fetch(user_id)

    def __init__(self, bot: commands.Bot):
        self.bucket = commands.CooldownMapping.from_cooldown(3, 600, commands.BucketType.member)
        self.bot = bot
        self._original_help_command = bot.help_command
        self.bot.help_command = AnimemesHelpFormat()
        self.bot.help_command.cog = self
        self.data_io = DataIO()
        self.checkers_channel = self.bot.get_channel(self.data_io.load_json("reddit_settings")["channel"])
        self.animemes_guild = self.bot.get_guild(187423852224053248)
        if self.animemes_guild:
            self.memester_role = self.animemes_guild.get_role(189594836687519744)
            self.new_memester = self.animemes_guild.get_role(653273427435847702)
            self.join_log = self.animemes_guild.get_channel(595585060909088774)
            self.rules_channel = self.animemes_guild.get_channel(366659034410909717)
            self.lockdown_channel = self.animemes_guild.get_channel(596319943612432404)
            self.horny_role = self.animemes_guild.get_role(722561738846896240)
            self.horny_jail = self.animemes_guild.get_role(639138311935361064)
        self.join_counter = 0
        self.join_limit = 5
        self.join_timer = 6
        with open("config/join_limit_settings.json") as f:
            settings = json.load(f)
            self.join_limit = settings["join_limit"]
            self.join_timer = settings["join_timer"]
        self.limit_reset.change_interval(hours=self.join_timer)
        self.word_filter = re.compile(r"(\bfagg*(ott*)?\b|\bretard)", re.IGNORECASE)
        self.nword_filter = re.compile(r"(?<!s)(?P<main>[n\U0001F1F3]+(?:(?P<_nc>.)(?P=_nc)*)?[i1!|l\U0001f1ee]+(?:(?P<_ic>.)(?P=_ic)*)?[g9\U0001F1EC](?:(?P<_gc>.)(?P=_gc)*)?[g9\U0001F1EC]+(?:(?P<_gc_>.)(?P=_gc_)*)?(?:[e3€£ÉÈëeÊêËéE\U0001f1ea]+(?:(?P<_ec>.)(?P=_ec)*)?[r\U0001F1F7]+|(?P<soft>[a\U0001F1E6])))((?:(?P<_rc>.)(?P=_rc)*)?[s5]+)?(?!rd)", re.IGNORECASE)

    async def cog_load(self):
        self.bot.loop.create_task(self.init_database())
        self.bot.loop.create_task(self.setup_rules_database())
        self.check_for_new_memester.start()

    async def cog_unload(self):
        self.bot.help_command = self._original_help_command
        self.check_for_new_memester.stop()
        self.limit_reset.cancel()

    @commands.command(name="stuck")
    async def people_stuck(self, ctx):
        """
        show how many people are still not able to read the rules
        """
        memester_count = len(self.memester_role.members) + len(self.new_memester.members)
        await ctx.send(embed=discord.Embed(title=f"People stuck in #{self.rules_channel.name}", description=f"There are currently {self.animemes_guild.member_count - memester_count:,} users stuck still reading the rules."))

    async def setup_rules_database(self):
        await self.bot.db.execute("""
        CREATE TABLE IF NOT EXISTS rule_channel (
            guild_id BIGINT NOT NULL primary key,
            channel_id BIGINT NOT NULL
        )
        """)

    @commands.group(name="rules", invoke_without_command=True)
    @commands.guild_only()
    @is_owner_or_moderator()
    async def rules(self, ctx: commands.Context):
        """
        A command for rewriting and posting the rules of the current server.
        The rules channel has to be setup via the `setup` subcommand.
        The command expects a text file to be uploaded on use.
        __Format rules__:
            - New lines of the original file are preserved.
            - Typical markdown rules apply `**bold**` `_italic_` etc.
            - An empty line tells the bot to post a new message otherwise the bot will fill up to 4000 character per message
            - to have an image in the embed use a single line starting with `!image` followed by the valid image url followed by an empty line
            - You have to use the [discord markdown](https://discord.com/developers/docs/reference#message-formatting) for channels, users, roles etc (check the link for more info)
              So instead of using @User you have to do `<@1234567890>` or instead of @Role you have to use `<&@1234456789>`
        """
        if not ctx.message.attachments:
            await ctx.send("Please upload a text file with the rules")
            return
        rules_channel_id = await self.bot.db.fetchval("""
        SELECT channel_id FROM rule_channel WHERE guild_id = $1
        """, ctx.guild.id)
        if rules_channel_id:
            rules_channel = ctx.guild.get_channel(rules_channel_id)
        else:
            return await ctx.send("no rules channel setup")
        attachment = ctx.message.attachments[0]
        bytesIO = BytesIO(await attachment.read())
        file_wrapper = TextIOWrapper(buffer=bytesIO, encoding='utf-8')
        paginator = commands.Paginator(prefix=None, suffix=None, max_size=4000)
        while (line := file_wrapper.readline()) != "":
            if line.strip() == "":
                paginator.close_page()
                continue
            paginator.add_line(line.strip("\n"))

        first_msg = None
        msg = None
        await rules_channel.purge(limit=None)
        for page in paginator.pages:
            if page.startswith("!image"):
                page = page.replace("!image ", "")
                embed = discord.Embed(colour=discord.Colour.blurple())
                embed.set_image(url=page)
            else:
                embed = discord.Embed(description=page, colour=discord.Colour.blurple())
            msg = await rules_channel.send(embed=embed)
            if not first_msg:
                first_msg = msg
        if first_msg and msg:
            await msg.edit(view=JumpMessageView(first_msg))

    @rules.command(name="setup")
    @commands.guild_only()
    @is_owner_or_moderator()
    async def setup_rules(self, ctx: commands.Context, rules_channel: discord.TextChannel):
        """
        Setup the channel where the rules for the `.rules` command are posted

        This command takes channel mention or channel id or channel name
        """
        await self.bot.db.execute("""
            INSERT INTO rule_channel(guild_id, channel_id) VALUES ($1, $2)
            ON CONFLICT (guild_id) 
            DO UPDATE SET channel_id = $2
        """, ctx.guild.id, rules_channel.id)
        await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")


    @tasks.loop(hours=1)
    async def limit_reset(self):
        self.join_counter = 0
        default_role = self.animemes_guild.default_role
        overwrite = self.rules_channel.overwrites_for(default_role)
        overwrite.send_messages = True
        await self.rules_channel.set_permissions(default_role, overwrite=overwrite)

    @is_owner_or_moderator()
    @commands.command(name="join_info", aliases=["ji", "joininfo"])
    async def get_join_info(self, ctx):
        """
        get info about how many people have joined and what the limit is
        """
        time_diff = None
        time_info = ""
        if self.limit_reset.is_running():
            time_diff = self.limit_reset.next_iteration - datetime.datetime.now(datetime.timezone.utc) 
            hours, minutes = divmod(time_diff.seconds, 3600)
            minutes, seconds = divmod(minutes, 60)
            time_info = (f"next iteration in {hours} hours and {minutes} minutes")
        await ctx.send(f"{self.join_counter} users have joined and the limit is {self.join_limit}\n"
                f"Task running: {self.limit_reset.is_running()} with a cooldown of {self.join_timer} hours {time_info}")


    @is_owner_or_moderator()
    @commands.command(name="join_limit", aliases=["jl"])
    async def set_join_limit(self, ctx, limit: int):
        """
        set the join limit for this server
        """
        if limit < 1:
            return await ctx.send("please choose a positive number bigger than 0")
        self.join_limit = limit
        await ctx.send(f"limit set to {self.join_limit}")
        with open("config/join_limit_settings.json", "w") as f:
            settings = {}
            settings["join_limit"] = self.join_limit
            settings["join_timer"] = self.join_timer
            json.dump(settings, f)

    @is_owner_or_moderator()
    @commands.command(name="join_timer", aliases=["jt", "jset", "jchange"])
    async def set_join_timer(self, ctx, hours: int, when: int = 0):
        """
        set a new join timer and also set in how many hours the task should start
        example:
        `.jt 6 8` which will make the task start every 6 hours after waiting 8 hours first
        """
        self.join_timer = hours
        was_running = self.limit_reset.is_running()
        self.limit_reset.cancel()
        self.limit_reset.change_interval(hours=hours)
        with open("config/join_limit_settings.json", "w") as f:
            settings = {}
            settings["join_limit"] = self.join_limit
            settings["join_timer"] = self.join_timer
            json.dump(settings, f)
        response = f"join timer cooldown changed to {hours} hours"
        if when > 0 :
            response += f" and will start running in {when} hours"
        await ctx.send(response)
        if was_running:
            def is_previous_lockdown_message(m):
                return "join limit was exceeded try again in" in m.content
            await self.lockdown_channel.purge(limit=100, check=is_previous_lockdown_message)
            await self.lockdown_channel.send(f"current join limit was exceeded try again in {when} hours")
            await asyncio.sleep(when * 3600)
            self.limit_reset.start()

    @is_owner_or_moderator()
    @commands.command(name="join_timer_start", aliases=["jstart"])
    async def start_join_timer(self, ctx, when: int = 0):
        """
        start the join timer either now or in x hours
        """
        self.limit_reset.cancel()
        if when > 0:
            await ctx.send(f"join timer will start in {when} hours")
            await asyncio.sleep(when * 3600)
        else:
            await ctx.send("join timer started")
        self.limit_reset.start()

    @is_owner_or_moderator()
    @commands.command(name="join_timer_stop", aliases=["jstop"])
    async def stop_join_timer(self, ctx):
        self.limit_reset.cancel()

    def build_join_message(self, member: discord.Member):
        embed = discord.Embed(title=f"{member} joined the server", colour=discord.Colour.blurple())
        embed.add_field(name="User", value=member.mention)
        embed.add_field(name="Account Creation",value=discord.utils.format_dt(member.created_at))
        embed.add_field(name="Server join", value=discord.utils.format_dt(member.joined_at))
        embed.set_thumbnail(url=member.display_avatar)
        embed.timestamp = datetime.datetime.now(tz=datetime.timezone.utc)

        return {'content': member.id, 'embed': embed}

    @commands.Cog.listener()
    async def on_message(self, message):
        channel = message.channel
        if message.author.id == self.bot.user.id or not message.guild:
            return
        if channel.id != self.rules_channel.id:
            return

        iam_memester_regex = re.compile(r'\.?i\s?a?m\s?meme?(ma)?st[ea]r', re.IGNORECASE)
        if iam_memester_regex.match(message.clean_content):
            await message.author.add_roles(self.new_memester)
            await message.delete()
            await self.join_log.send(**self.build_join_message(message.author))
            if self.limit_reset.is_running():
                self.join_counter += 1
            if self.join_counter >= self.join_limit and self.join_limit > 0 and self.limit_reset.is_running():
                default_role = message.guild.default_role
                overwrite = message.channel.overwrites_for(default_role)
                overwrite.send_messages = False
                await self.rules_channel.set_permissions(default_role, overwrite=overwrite)
                time_diff = self.limit_reset.next_iteration - datetime.datetime.now(datetime.timezone.utc) 
                if self.lockdown_channel:
                    def is_previous_lockdown_message(m):
                        return "join limit was exceeded try again in" in m.content
                    await self.lockdown_channel.purge(limit=100, check=is_previous_lockdown_message)
                    await self.lockdown_channel.send(f"current join limit was exceeded try again in {round(time_diff.seconds / 3600)} hours")
            return
        content = message.content.lower()
        with open("data/rules_channel_phrases.json") as f:
            phrases = json.load(f)
            curses = ["fuck you", "fuck u", "stupid bot", "fucking bot"]
            has_confirm_in_message = "yes" in content or "i have" in content
            if "gaston is always tight" in content.lower():
                await channel.send(choice(phrases["tight"]))
                return
            if any([c in content for c in curses]):
                await channel.send(choice(phrases["curse"]))
                return
            if message.role_mentions:
                await channel.send(choice(phrases["pinged"]))
                return
            if has_confirm_in_message:
                if self.bucket.update_rate_limit(message):
                    await channel.send(choice(phrases['repeat']))
                    return
                await channel.send(choice(phrases["yes"]))
                return
            if "sex-shack" in content:
                if self.bucket.update_rate_limit(message):
                    await channel.send(choice(phrases['repeat']))
                    return
                await channel.send(choice(phrases["shack"]))
                return
            if "general-discussion" in content or re.match(r"#(\w+-?)+", content) or message.channel_mentions:
                if self.bucket.update_rate_limit(message):
                    await channel.send(choice(phrases['repeat']))
                    return
                await channel.send(choice(phrases["channel"]))
                return

    async def fetch_member_via_api(self, user_id):
        """
        for fetching the user via the api if the member may not be in the cache
        """
        try:
            return await self.animemes_guild.fetch_member(user_id)
        except Exception as e:
            logger = logging.getLogger("PoutyBot")
            logger.warning(f"Could not fetch user with user id {user_id}")
            return None

    @tasks.loop(minutes=1)
    async def check_for_new_memester(self):
        if not self.animemes_guild:
            return
        rows = await self.fetch_new_memesters()
        try:
            for row in rows:
                if row["time_over"] < datetime.datetime.utcnow():
                    member = self.animemes_guild.get_member(row["user_id"])
                    if member is None:
                        member = await self.fetch_member_via_api(row["user_id"])
                    if member:
                        await member.add_roles(self.memester_role)
                        await member.remove_roles(self.new_memester)
                    await self.remove_user_from_new_list(row["user_id"])
        except (discord.NotFound):
            await self.remove_user_from_new_list(row["user_id"])
        except (discord.Forbidden, discord.HTTPException):
            logger = logging.getLogger("PoutyBot")
            logger.error(traceback.format_exc())
        except Exception as e: 
            logger = logging.getLogger("PoutyBot")
            logger.error("memester check was cancelled", exc_info=1)
            owner = self.bot.get_user(self.bot.owner_id)
            lines = traceback.format_exc().splitlines()
            paginator = commands.Paginator()
            paginator.add_line("check_for_new_memester failed")
            for line in lines:
                paginator.add_line(line)
            for page in paginator.pages:
                await owner.send(page)

    @check_for_new_memester.after_loop
    async def memester_check_error(self):
        if self.check_for_new_memester.failed():
            await asyncio.sleep(3600)
            self.check_for_new_memester.restart()

    @commands.Cog.listener(name="on_member_update")
    async def new_memester_assigned(self, before, after):
        if self.new_memester in before.roles:
            return
        if self.new_memester not in before.roles and self.new_memester not in after.roles:
            return
        if self.memester_role in after.roles and self.new_memester not in before.roles:
            await after.remove_roles(self.memester_role)
        if self.new_memester:
            await after.add_roles(self.new_memester)
        await self.add_new_memester(after)

    @commands.Cog.listener(name="on_member_update")
    async def horny_jail_check(self, _: discord.Member, after: discord.Member):
        if self.horny_jail in after.roles and self.horny_role in after.roles:
            await after.remove_roles(self.horny_role)

    @commands.Cog.listener(name="on_guild_role_update")
    async def update_memester_color(self, before, after: discord.Role):
        if after == self.memester_role:
            color = after.color
            await self.new_memester.edit(color=color)

    async def check_member_for_valid_character(self, member) -> bool:
        def name_check(c):
            return c.isascii() or c.isdigit()
        valid_chars_nick = ""
        if member.nick:
            valid_chars_nick = list(filter(name_check, member.nick))
        valid_chars_name = list(filter(name_check, member.name))
        if len(valid_chars_nick) >=1 or len(valid_chars_name) >= 1:
            return True
        return False

    @commands.Cog.listener(name="on_member_update")
    async def check_member_name(self, before, after):
        if self.memester_role not in after.roles and self.new_memester not in after.roles:
            return
        forbidden_match = self.word_filter.search(after.display_name.lower())
        old_name = after.display_name
        if not await self.check_member_for_valid_character(after):
            await after.edit(nick=f"pingable_username#{after.discriminator}")
        elif forbidden_match:
            await after.edit(nick=f"bad_name#{after.discriminator}")
            if self.checkers_channel:
                await self.checkers_channel.send(f"changed {after.mention}'s nickname was {old_name} before.")
        else:
            return

    @commands.Cog.listener(name="on_message")
    async def rules_channel_word_filter(self, message: discord.Message):
        if message.channel != self.rules_channel:
            return

        if (match := self.word_filter.search(message.content)) or (match := self.nword_filter.search(message.content)):
            if "Using slurs such as but not limited to" in message.content:
                return
            embed = discord.Embed(title="Wordfilter Ban", description=f"{message.author.mention} was banned for saying `{match.group(0)}` in {self.rules_channel.mention}")
            embed.add_field(name="Username", value=message.author.display_name)
            embed.add_field(name="User", value=message.author.mention)
            embed.add_field(name="User id", value=message.author.id)
            embed.add_field(name="Message", value=f"[Jump to Message]({message.jump_url})")
            try:
                await message.author.send("You've been banned from the official /r/Animemes server for triggering the word filter before even entering the server.\n"+
                f"You've said `{match.group(0)}`.\n"+ 
                "If you think this ban was in error you can appeal by dming any of the mods.")
            except:
                pass
            try:
                await message.author.ban(delete_message_days=0, reason=f"word ban filter with: {match.group(0)}")
            except (discord.HTTPException, discord.Forbidden):
                await self.checkers_channel.send("**USER BAN FAILED MANUAL BAN NEEDED**")
            await self.checkers_channel.send(embed=embed)
            

    @commands.Cog.listener(name="on_user_update")
    async def check_user_name(self, before, after):
        after = self.animemes_guild.get_member(after.id)
        if not after:
            return
        if self.memester_role not in after.roles and self.new_memester not in after.roles:
            return
        forbidden_match = self.word_filter.search(after.display_name.lower())
        old_name = after.display_name
        if not await self.check_member_for_valid_character(after):
            await after.edit(nick=f"pingable_username#{after.discriminator}")
        elif forbidden_match:
            await after.edit(nick=f"bad_name#{after.discriminator}")
            if self.checkers_channel:
                await self.checkers_channel.send(f"changed {after.mention}'s nickname was {old_name} before.")
        else:
            return

    @commands.command(name="adduser")
    async def add_user(self, ctx, user: discord.Member):
        await user.add_roles(self.new_memester)
        await self.join_log.send(**self.build_join_message(user))


async def setup(bot: commands.Bot):
    await bot.add_cog(ReadRules(bot))

