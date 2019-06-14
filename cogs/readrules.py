from discord.ext import commands
import json
from random import choice
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
        self.bot = bot
        self._original_help_command = bot.help_command
        self.bot.help_command = AnimemesHelpFormat()
        self.bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.id == self.bot.user.id:
            return
        content = message.content.lower()
        with open("data/rules_channel_phrases.json") as f:
            phrases = json.load(f)
            has_confirm_in_message = "yes" in content or "i have" in content
            if has_confirm_in_message and message.channel.id == 366659034410909717:
                await message.channel.send(choice(phrases["yes"]))


def setup(bot: commands.Bot):
    bot.add_cog(ReadRules(bot))

