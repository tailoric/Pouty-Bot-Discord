import discord
import logging
from .utils.exceptions import *
from .utils import checks
from .utils.dataIO import DataIO
from discord.ext.commands import DefaultHelpCommand


class CustomHelpCommand(DefaultHelpCommand):

    async def send_bot_help(self, mapping):
        self.paginator.add_line(self.context.bot.description)
        self.paginator.add_line(empty=True)
        self.paginator.add_line("Command categories:")
        for cog in mapping:
            filtered = await self.filter_commands(mapping.get(cog))
            if cog is None or len(filtered) == 0 or cog.qualified_name is "Default":
                continue
            if cog.qualified_name:
                self.paginator.add_line("\t* {0}".format(cog.qualified_name))
            if cog.description:
                self.paginator.add_line("\t\t\"{0}\"".format(cog.description))
        self.paginator.add_line("To see more information about the commands of a category use .help <CategoryName>")
        self.paginator.add_line("ATTENTION: The categories are case sensitive")
        await self.send_pages()


class Default(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._original_help_command = bot.help_command
        self.bot.help_command = CustomHelpCommand()
        self.bot.help_command.cog = self
        self.bot.add_listener(self.on_ready, 'on_ready')
        self.bot.add_listener(self.on_command_error, "on_command_error")
        self.bot.add_check(self.check_for_black_list_user, call_once=True)
        self.bot.add_check(self.check_disabled_command, call_once=True)
        self.data_io = DataIO()
        self.credentials = self.data_io.load_json("credentials")
        self.logger = logging.getLogger("PoutyBot")

    def cog_unload(self):
        self.bot.remove_listener(self.on_ready, 'on_ready')
        self.bot.remove_listener(self.on_command_error, "on_command_error")
        self.bot.remove_check(self.check_for_black_list_user, call_once=True)
        self.bot.remove_check(self.check_disabled_command, call_once=True)
        self.bot.help_command = self._original_help_command

    async def on_ready(self):
        print('Logged in as')
        print(self.bot.user.name)
        print(self.bot.user.id)
        print('-'*8)
        try:
            init_extensions = self.data_io.load_json("initial_cogs")
            for extension in init_extensions:
                self.bot.load_extension(extension)
            print(discord.utils.oauth_url(self.credentials['client-id']))
        except Exception as e:
            print('Failed to load extension {}\n{}: {}'.format(extension, type(e).__name__, e))

    async def on_command_error(self, ctx, error):
        error_message_sent = False
        self.logger.log(logging.INFO, f"{type(error)}; {error}")
        if isinstance(error, BlackListedException):
            return
        if isinstance(error, DisabledCommandException):
            await ctx.message.channel.send("Command is disabled")
            error_message_sent = True
        if isinstance(error, commands.CheckFailure) and not error_message_sent:
            await ctx.message.channel.send("You don't have permission to use this command")
            error_message_sent = True
        if not isinstance(error, commands.CommandNotFound) and not error_message_sent:
            await ctx.message.channel.send(error)
            if ctx.command.help is not None:
                await ctx.message.channel.send("```\n{}\n```".format(ctx.command.help))

    async def check_disabled_command(self, ctx):
        owner_cog = self.bot.get_cog("Owner")
        if owner_cog:
            current_guild = ctx.guild
            disabled_commands = [dc["command"]
                                 for dc in owner_cog.disabled_commands if dc["server"] == current_guild.id]
            if ctx.command.name in disabled_commands and not checks.user_is_in_whitelist_server(self.bot, ctx.author):
                raise DisabledCommandException(f"{ctx.author.name}#{ctx.author.discriminator} used disabled command")
        return True

    async def check_for_black_list_user(self, ctx):
        owner_cog = self.bot.get_cog("Owner")
        if owner_cog:
            if ctx.author.id in owner_cog.global_ignores:
                bl_user = ctx.author
                raise BlackListedException(f"blacklisted user: {bl_user.name}#{bl_user.discriminator} ({bl_user.id}) "
                                           f"tried to use command")
        return True


def setup(bot: commands.Bot):
    bot.add_cog(Default(bot))

