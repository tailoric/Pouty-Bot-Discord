import discord
import logging
from .utils.exceptions import *
from .utils import checks
from .utils.dataIO import DataIO
from discord.ext.commands import DefaultHelpCommand
import traceback


class CustomHelpCommand(DefaultHelpCommand):

    async def send_bot_help(self, mapping):
        self.paginator.add_line(self.context.bot.description, empty=True)
        self.paginator.add_line("To see more information about the commands of a category use .help <CategoryName>")
        self.paginator.add_line("ATTENTION: The categories are case sensitive", empty=True)
        self.paginator.add_line("Command categories:")
        for cog in mapping:
            filtered = await self.filter_commands(mapping.get(cog))
            if cog is None or len(filtered) == 0 or cog.qualified_name is "Default":
                continue
            if cog.qualified_name:
                self.paginator.add_line("\t* {0}".format(cog.qualified_name))
            if cog.description:
                self.paginator.add_line("\t\t\"{0}\"".format(cog.description))
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
        handler = logging.FileHandler(filename='data/pouty.log', encoding='utf-8', mode='a')
        handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        self.logger.addHandler(handler)
        self.dm_logger = logging.getLogger("DMLogger")
        self.dm_logger.setLevel(logging.INFO)
        handler = logging.FileHandler(filename='data/dms.log', encoding='utf-8', mode='a')
        handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        self.dm_logger.addHandler(handler)


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
        print(discord.utils.oauth_url(self.credentials['client-id']))
        print('-'*8)
        init_extensions = self.data_io.load_json("initial_cogs")
        for extension in init_extensions:
            try:
                self.bot.load_extension(extension)
            except Exception as e:
                print('Failed to load extension {}\n{}: {}'.format(extension, type(e).__name__, e))
                continue

    @commands.Cog.listener()
    async def on_message(self, message):
        if isinstance(message.channel, discord.DMChannel):
            user = message.author
            self.dm_logger.info(f"{user.name}#{user.discriminator}({user.id}) message: {message.content}")


    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, BlackListedException):
            return
        elif isinstance(error, DisabledCommandException):
            await ctx.message.channel.send("Command is disabled")
            return
        elif isinstance(error, commands.BadArgument):
            await ctx.send(error)
            if ctx.command.help is not None:
                await ctx.send_help(ctx.command)
        else:
            await ctx.send(error)


    async def check_disabled_command(self, ctx):
        owner_cog = self.bot.get_cog("Owner")
        if owner_cog:
            if checks.user_is_in_whitelist_server(self.bot, ctx.author):
                return True
            current_guild = ctx.guild
            guilds_with_disabled_command = [g["server"] for g in owner_cog.disabled_commands ]
            if current_guild:
                disabled_commands = [dc["command"] for dc in owner_cog.disabled_commands
                                     if dc["server"] == current_guild.id]
                if ctx.command.name in disabled_commands:
                    raise DisabledCommandException(f"{ctx.author.name}#{ctx.author.discriminator} used disabled command")
            else:
                for guild_id in guilds_with_disabled_command:
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        continue
                    member = guild.get_member(ctx.author.id)
                    if not member:
                        continue
                    disabled_commands = [dc["command"] for dc in owner_cog.disabled_commands
                                         if dc["server"] == guild.id]
                    if ctx.command.name in disabled_commands:
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

