from discord.ext import commands
import json
from random import choice
import re
from .utils.dataIO import DataIO
class AnimemesHelpFormat(commands.DefaultHelpCommand):


    def random_response(self):
        with open("data/rules_channel_phrases.json")as f:
            phrases = json.load(f)
            return choice(phrases["help"])


    async def send_bot_help(self, mapping):
        channel = self.context.channel
        ignore_cogs = ["Default", "ReadRules"]
        if channel and channel.id == 366659034410909717:
            await self.context.send(self.random_response())
            return
        self.paginator.add_line(self.context.bot.description, empty=True)
        self.paginator.add_line("To see more information about the commands of a category use .help <CategoryName>")
        self.paginator.add_line("ATTENTION: The categories are case sensitive", empty=True)
        self.paginator.add_line("Command categories:")
        for cog in mapping:
            filtered = await self.filter_commands(mapping.get(cog))
            if cog is None or len(filtered) == 0 or cog.qualified_name in ignore_cogs:
                continue
            if cog.qualified_name:
                self.paginator.add_line("\t* {0}".format(cog.qualified_name))
            if cog.description:
                self.paginator.add_line("\t\t\"{0}\"".format(cog.description))
        await self.send_pages()

class ReadRules(commands.Cog):
    def __init__(self, bot : commands.Bot):
        self.bucket = commands.CooldownMapping.from_cooldown(3, 600, commands.BucketType.member)
        self.bot = bot
        self._original_help_command = bot.help_command
        self.bot.help_command = AnimemesHelpFormat()
        self.bot.help_command.cog = self
        self.data_io = DataIO()
        self.checkers_channel = self.bot.get_channel(self.data_io.load_json("reddit_settings")["channel"])
        self.animemes_guild = self.bot.get_guild(187423852224053248)
        self.memester_role = self.animemes_guild.get_role(189594836687519744)
        self.join_log = self.animemes_guild.get_channel(595585060909088774)

    def cog_unload(self):
        self.bot.help_command = self._original_help_command

    @commands.Cog.listener()
    async def on_message(self, message):
        channel = message.channel
        if message.author.id == self.bot.user.id or not message.guild:
            return
        if channel.id != 366659034410909717:
            return
        iam_memester_regex = re.compile(r'i\s?am\s?meme?(ma)?st[ea]r', re.IGNORECASE)
        if iam_memester_regex.search(message.clean_content):
            await message.author.add_roles(self.memester_role)
            await message.delete()
            await self.join_log.send(f"{message.author.mention} joined the server.")
            return
        content = message.content.lower()
        with open("data/rules_channel_phrases.json") as f:
            phrases = json.load(f)
            has_confirm_in_message = "yes" in content or "i have" in content
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

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if self.memester_role and self.memester_role not in after.roles:
            return
        alphanumeric_pattern = re.compile(r'.*[a-zA-Z0-9\_\.\,\[\](\\)\'\"\:\;\<\>\*\!\#\$\%\^\&\=\/\`\+\-\~\:\;\@\|]{1,}.*', re.ASCII)
        forbidden_word_pattern = re.compile(r'(trap|nigg(a|er)|fag(got)?)')
        match_name = alphanumeric_pattern.match(after.name)
        match_nickname = None
        if after.nick:
            match_nickname = alphanumeric_pattern.match(after.nick)
        forbidden_match = forbidden_word_pattern.search(after.display_name)
        old_name = after.display_name
        if not match_nickname and not match_name:
            await after.edit(nick="pingable_username")
        elif not match_name and not after.nick:
            await after.edit(nick="pingable_username")
        elif forbidden_match:
            new_nick = forbidden_word_pattern.sub('*', after.display_name)
            await after.edit(nick=new_nick)
        else:
            return
        if self.checkers_channel:
            await self.checkers_channel.send(f"changed {after.mention}'s nickname was {old_name} before.")



def setup(bot: commands.Bot):
    bot.add_cog(ReadRules(bot))

