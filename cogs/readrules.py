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
from cogs.default import CustomHelpCommand

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
        self.memester_role = self.animemes_guild.get_role(189594836687519744)
        self.new_memester = self.animemes_guild.get_role(653273427435847702)
        self.join_log = self.animemes_guild.get_channel(595585060909088774)
        self.bot.loop.create_task(self.init_database())
        self.check_for_new_memester.start()

    def cog_unload(self):
        self.bot.help_command = self._original_help_command
        self.check_for_new_memester.stop()

    @commands.Cog.listener()
    async def on_message(self, message):
        channel = message.channel
        if message.author.id == self.bot.user.id or not message.guild:
            return
        if channel.id != 366659034410909717:
            return
        iam_memester_regex = re.compile(r'\.?i\s?am\s?meme?(ma)?st[ea]r', re.IGNORECASE)
        if iam_memester_regex.match(message.clean_content):
            await message.author.add_roles(self.new_memester)
            await message.delete()
            await self.join_log.send(f"{message.author.mention} joined the server.")
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

    @tasks.loop(minutes=1)
    async def check_for_new_memester(self):
        rows = await self.fetch_new_memesters()
        try:
            for row in rows:
                if row["time_over"] < datetime.datetime.utcnow():
                    member = self.animemes_guild.get_member(row["user_id"])
                    if member:
                        await member.add_roles(self.memester_role)
                        await member.remove_roles(self.new_memester)
                    await self.remove_user_from_new_list(row["user_id"])
        except (discord.Forbidden, discord.HTTPException):
            logger = logging.getLogger("PoutyBot")
            logger.error(traceback.format_exc())
        except Exception as e: 
            logger = logging.getLogger("PoutyBot")
            logger.error("memester check was cancelled", exc_info=1)
            owner = self.bot.get_user(self.bot.owner_id)
            await owner.send(f"`check_for_new_memester` failed\n```\n{traceback.format_exc()}\n```")

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

    @commands.Cog.listener(name="on_guild_role_update")
    async def update_memester_color(self, before, after: discord.Role):
        if after == self.memester_role:
            color = after.color
            await self.new_memester.edit(color=color)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if self.memester_role not in after.roles and self.new_memester not in after.roles:
            return
        if before.display_name == after.display_name:
            return
        alphanumeric_pattern = re.compile(r'.*[a-zA-Z0-9\_\.\,\[\](\\)\'\"\:\;\<\>\*\!\#\$\%\^\&\=\/\`\+\-\~\:\;\@\|]{1,}.*', re.ASCII)
        forbidden_word_pattern = re.compile(r'(\btrap\b|nigg(a|er)|fag(got)?)')
        match_name = alphanumeric_pattern.match(after.name.lower())
        match_nickname = None
        if after.nick:
            match_nickname = alphanumeric_pattern.match(after.nick)
        forbidden_match = forbidden_word_pattern.search(after.display_name.lower())
        old_name = after.display_name
        if not match_nickname and not match_name:
            await after.edit(nick="pingable_username")
        elif not match_name and not after.nick:
            await after.edit(nick="pingable_username")
        elif forbidden_match:
            new_nick = forbidden_word_pattern.sub('*', after.display_name.lower())
            await after.edit(nick=new_nick)
        else:
            return
        if self.checkers_channel:
            await self.checkers_channel.send(f"changed {after.mention}'s nickname was {old_name} before.")



def setup(bot: commands.Bot):
    bot.add_cog(ReadRules(bot))

