import discord
import logging
from .utils.exceptions import *
from .utils import checks
from .utils.dataIO import DataIO
from .utils import paginator
from discord.ext.commands import DefaultHelpCommand
import traceback


def levenshtein_distance(user_input: str, command_name: str):
    rows = len(user_input) + 1
    cols = len(command_name) + 1
    dist = [[0 for x in range(cols)] for x in range(rows)]
    for i in range(1, rows):
        dist[i][0] = i
    for i in range(1, cols):
        dist[0][i] = i

    for col in range(1, cols):
        for row in range(1, rows):
            if user_input[row - 1] == command_name[col - 1]:
                cost = 0
            else:
                cost = 1
            dist[row][col] = min(dist[row-1][col] + 1,
                                 dist[row][col-1] + 1,
                                 dist[row-1][col-1] + cost)
    return dist[-1][-1]


class CustomHelpCommand(DefaultHelpCommand):

    async def send_bot_help(self, mapping):
        entries = []
        for cog in mapping:
            entry = []
            filtered = await self.filter_commands(mapping.get(cog))
            if cog is None or len(filtered) == 0 or cog.qualified_name == "Default":
                continue
            if cog.qualified_name:
                entry.append(cog.qualified_name)
            if filtered:
                entry.append("\t\n".join([f"**{command.name}**:\n{command.short_doc}" for command in filtered]))
            entries.append(entry)
        help_page = paginator.FieldPages(self.context, entries=entries, per_page=1)
        await help_page.paginate()

    async def command_not_found(self, string):
        filtered_commands = await self.filter_commands(self.context.bot.commands, sort=True)
        distances = []
        for command in filtered_commands:
            distance = levenshtein_distance(string, command.name)
            distances.append({"name":command.name, "distance" : distance})
        list_sorted = sorted(distances, key=lambda element: element["distance"])
        same_dst_results = [c["name"] for c in list_sorted if c["distance"] == list_sorted[0]["distance"]]
        return (f"No command called `{string}` found."
                f" Maybe you meant one of the following command(s):\n`{same_dst_results}`")

    async def send_cog_help(self, cog):
        embed = discord.Embed()
        embed.title = cog.qualified_name
        embed.description = cog.description if cog.description else discord.Embed.Empty
        filtered_commands = await self.filter_commands(cog.get_commands(), sort=True)
        for command in filtered_commands:
            command_title = f"{command.name} [{', '.join(command.aliases)}]" if command.aliases \
                else f"{command.name}"
            embed.add_field(name=command_title, value=command.short_doc if command.short_doc else "\u200b")
        embed.set_footer(text="[] means aliases for the command. "
                              "Use '.help command' (without quotes) for more help for a certain command ")
        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        embed = discord.Embed()
        embed.title = f"{self.clean_prefix}{command.qualified_name} {command.signature}"
        embed.description = command.help if command.help else discord.Embed.Empty
        embed.set_footer(text="<> means parameter is required, [] means parameter is optional")
        if command.aliases:
            embed.add_field(name="aliases", value=", ".join(command.aliases), inline=True)
        if command.usage:
            embed.add_field(name="usage", value=command.usage, inline=True)
        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group):
        embed = discord.Embed()
        embed.title = f"{self.clean_prefix}{group.qualified_name} {group.signature}"
        embed.description = group.help if group.help else discord.Embed.Empty
        embed.set_footer(text="<> means parameter is required, [] means parameter is optional")
        if group.aliases:
            embed.add_field(name="aliases", value=", ".join(group.aliases), inline=False)
        if group.usage:
            embed.add_field(name="usage", value=group.usage, inline=False)
        if group.commands:
            embed.add_field(name="Commands", value=f"\n"
                            .join([f"{command.qualified_name}: {command.short_doc}" for command in group.commands]),
                            inline=False)
        await self.get_destination().send(embed=embed)


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
        self.bot.loop.create_task(self.load_cogs())

    async def load_cogs(self):
        if hasattr(self.bot, 'extensions_loaded'):
            return
        await self.bot.wait_for('ready')
        init_extensions = self.data_io.load_json("initial_cogs")
        for extension in init_extensions:
            try:
                self.bot.load_extension(extension)
            except Exception as e:
                print('Failed to load extension {}\n{}: {}'.format(extension, type(e).__name__, e))
                continue
        self.bot.extensions_loaded = True
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
        print('-' * 8)

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
        if isinstance(error, commands.CommandOnCooldown):
            return
        if isinstance(error, DisabledCommandException):
            await ctx.message.channel.send("Command is disabled")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)
            if ctx.command.help is not None:
                await ctx.send_help(ctx.command)
            return
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send(error.original)
            error_msg = ""
            if hasattr(ctx.command, 'name'):
                error_msg += f"{ctx.command.name} error:\n"
            error_msg += f"{error}\n"
            error_msg += f"message jump url: {ctx.message.jump_url}\n"
            error_msg += f"message content: {ctx.message.content}\n"
            self.logger.error(error_msg, exc_info=True)
        else:
            error_msg = ""
            if hasattr(ctx.command, 'name'):
                error_msg += f"{ctx.command.name} error:\n"
            error_msg += f"{error}\n"
            error_msg += f"message jump url: {ctx.message.jump_url}\n"
            error_msg += f"message content: {ctx.message.content}\n"
            self.logger.error(error_msg, exc_info=True)

    async def check_disabled_command(self, ctx):
        owner_cog = self.bot.get_cog("Owner")
        if owner_cog:
            if checks.user_is_in_whitelist_server(self.bot, ctx.author):
                return True
            current_guild = ctx.guild
            guilds_with_disabled_command = [g["server"] for g in owner_cog.disabled_commands]
            if current_guild:
                disabled_commands = [dc["command"] for dc in owner_cog.disabled_commands
                                     if dc["server"] == current_guild.id]
                if ctx.command.name in disabled_commands:
                    raise DisabledCommandException(
                        f"{ctx.author.name}#{ctx.author.discriminator} used disabled command")
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
                        raise DisabledCommandException(
                            f"{ctx.author.name}#{ctx.author.discriminator} used disabled command")
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
