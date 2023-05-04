from discord import app_commands
from .utils import checks
from .utils import paginator
from .utils import views
from .utils.dataIO import DataIO
from .utils.exceptions import *
from discord.ext.commands import DefaultHelpCommand, Paginator
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from discord.ext import menus
from dataclasses import dataclass, field
from typing import List, Union
import textwrap
import discord
import logging
import traceback


LOG_SIZE = 200 * 1024 * 1024

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

@dataclass
class CogPage:
    cog: commands.Cog
    commands: list[Union[commands.Command, commands.Group]]

class CommandsSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, prefix: str, commands: List[Union[commands.Command, commands.Group]]):
        self.bot = bot
        self.prefix = prefix
        super().__init__(
                placeholder="Select command",
                options=[discord.SelectOption(label=command.qualified_name, value=command.name) for command in commands],
                max_values=1,
                row=0
                )

    async def callback(self, interaction: discord.Interaction):
        command = self.bot.get_command(self.values[0])
        if command:
            title = f"{self.prefix}{command.usage}" if command.usage else f"{self.prefix}{command.name} {command.signature}"
            embed = discord.Embed(
                    title=title,
                    colour=discord.Colour.blurple(),
                    description=command.help or None
                    )
            embed.set_footer(text="<> means parameter is required, [] means parameter is optional, word: means it is a flag")
            if isinstance(command, commands.Group):
                embed.add_field(name="**Subcommands**", value="\u200b", inline=False)
                for c in command.commands:
                    embed.add_field(name=f"`{self.prefix}{c.qualified_name}`", value=c.short_doc or "\u200b" ) 
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("Command not found something went wrong", ephemeral=True)


class BotHelpView(views.PaginatedView):
    def __init__(self,  *, source: 'BotHelpPages'):
        self.select = None
        super().__init__(source=source)
    
    async def start(self, ctx: commands.Context):
        page : CogPage = await self._source.get_page(0)
        self.select = CommandsSelect(ctx.bot, ctx.clean_prefix, page.commands)
        self.add_item(self.select)
        for child in self.children:
            child.row = 2
        await super().start(ctx)

    async def show_page(self, page_number: int):
        page : CogPage = await self._source.get_page(page_number)
        if self.select:
            self.select.options = [discord.SelectOption(label=command.qualified_name, value=command.name) for command in page.commands]
        await super().show_page(page_number)

class BotHelpPages(menus.ListPageSource):
    def __init__(self, entries: list[CogPage]):
        super().__init__(entries, per_page=1)

    async def format_page(self, menu: BotHelpView, page: CogPage):
        embed = discord.Embed(
                    title=page.cog.qualified_name,
                    color=discord.Colour.blurple()
                )
        for command in page.commands:
            embed.add_field(name=command.qualified_name, value=command.short_doc or "\u200b", inline=False)
            if len(embed) > 5000:
                break
        embed.set_footer(text=f"Page {menu.current_page+1}/{self.get_max_pages()}")
        return embed


class CustomHelpCommand(DefaultHelpCommand):

    async def send_bot_help(self, mapping):
        entries = []
        for cog in mapping:
            filtered = await self.filter_commands(mapping.get(cog))
            if cog is None or len(filtered) == 0 or cog.qualified_name == "Default":
                continue
            entries.append(CogPage(cog, filtered))
        source = BotHelpPages(entries=entries)
        view = BotHelpView(source=source)
        await view.start(self.context)

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
        embed.description = cog.description if cog.description else None
        filtered_commands = await self.filter_commands(cog.get_commands(), sort=True)
        for command in filtered_commands:
            command_title = f"{command.name} [{', '.join(command.aliases)}]" if command.aliases \
                else f"{command.name}"
            embed.add_field(name=command_title, value=command.short_doc if command.short_doc else "\u200b")
        embed.set_footer(text="[] means aliases for the command. "
                              "Use '.help command' (without quotes) for more help for a certain command ")
        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        embed = discord.Embed(colour=discord.Colour.blurple())
        if not command.usage:
            embed.title = f"{self.context.clean_prefix}{command.qualified_name} {command.signature}"
        else:
            embed.title = f"{self.context.clean_prefix}{command.usage}"
        embed.description = command.help if command.help else None
        embed.set_footer(text="<> means parameter is required, [] means parameter is optional, word: means it is a flag")
        if command.aliases:
            embed.add_field(name="aliases", value=", ".join(command.aliases), inline=True)
        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group):
        embed = discord.Embed(colour=discord.Colour.blurple())
        if group.usage:
            embed.title = f"{self.context.clean_prefix}{group.usage}"
        else:
            embed.title = f"{self.context.clean_prefix}{group.qualified_name} {group.signature}"
        embed.description = group.help if group.help else None
        embed.set_footer(text="<> means parameter is required, [] means parameter is optional, word: means it is a flag")
        if group.aliases:
            embed.add_field(name="aliases", value=", ".join(group.aliases), inline=False)
        if group.commands:
            embed.add_field(name="**Subcommands**", value="\u200b", inline=False)
            for c in group.commands:
                embed.add_field(name=f"`{self.context.clean_prefix}{c.qualified_name}`", value=c.short_doc or "\u200b" ) 
        await self.get_destination().send(embed=embed)


class Default(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.debug = False
        self._original_help_command = bot.help_command
        self.bot.help_command = CustomHelpCommand()
        self.bot.help_command.cog = self
        self.bot.add_listener(self.on_ready, 'on_ready')
        self.bot.add_listener(self.on_command_error, "on_command_error")
        self.bot.add_check(self.check_for_black_list_user, call_once=True)
        self.bot.add_check(self.check_disabled_command, call_once=True)
        self.bot.tree.on_error = self.app_command_error
        self.data_io = DataIO()
        self.credentials = self.data_io.load_json("credentials")
        self.logger = logging.getLogger("PoutyBot")
        if not len(self.logger.handlers) > 0:
            handler = RotatingFileHandler(filename='data/pouty.log',
                    encoding='utf-8',
                    mode='a',
                    maxBytes=LOG_SIZE,
                    backupCount=2
                    )
            handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
            self.logger.addHandler(handler)
        self.dm_logger = logging.getLogger("DMLogger")
        if not len(self.dm_logger.handlers) > 0:
            self.dm_logger.setLevel(logging.INFO)
            handler = RotatingFileHandler(filename='data/dms.log',
                    encoding='utf-8',
                    mode='a', 
                    maxBytes=LOG_SIZE,
                    backupCount=2)
            handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
            self.dm_logger.addHandler(handler)

    async def cog_load(self):
        await self.bot.wait_until_ready()
        await self.create_loaded_cogs_table()
        await self.load_cogs()

    async def create_loaded_cogs_table(self):
        await self.bot.db.execute("""
        CREATE TABLE IF NOT EXISTS cogs (
            module TEXT NOT NULL PRIMARY KEY
        )
        """)
    async def load_cogs(self):
        if hasattr(self.bot, 'extensions_loaded'):
            return
        init_extensions = [ext["module"] for ext in await self.bot.db.fetch("""SELECT module FROM cogs""")]
        for extension in init_extensions:
            try:
                await self.bot.load_extension(extension)
            except Exception as e:
                self.logger.exception('Failed to load extension: %s', e)
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
        print(f'discord.py version: {discord.__version__}')
        print('-' * 8)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild and not message.flags.ephemeral:
            user = message.author
            self.dm_logger.info(f"{user}({user.id}) message: {message.content}")

    async def on_command_error(self, ctx, error):
        if ctx.command and ctx.command.has_error_handler():
            return
        elif isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, BlackListedException):
            return
        elif isinstance(error, commands.CommandOnCooldown):
            await self.cooldown_embed(ctx, error)
            return
        elif isinstance(error, DisabledCommandException):
            await ctx.message.channel.send("Command is disabled")
            return
        elif isinstance(error, commands.BadArgument) or isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(error)
            if ctx.command.help is not None:
                await ctx.send_help(ctx.command)
            return
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(error, ephemeral=True)
            return
        elif isinstance(error, commands.CommandInvokeError):
            await self.create_and_send_traceback(ctx, error.original)
        else:
            await self.create_and_send_traceback(ctx, error)

    async def cooldown_embed(self, ctx, error):
            minutes, seconds = divmod(error.retry_after, 60)
            if ctx.guild and ctx.guild.me.colour:
                colour = ctx.guild.me.colour
            else:
                colour = discord.Colour.blurple()
            return await ctx.send(embed=discord.Embed(title=ctx.command.qualified_name.title(),
                description=f"On cooldown retry after {int(minutes)} min and {int(seconds)} sec",
                timestamp=datetime.utcnow() + timedelta(seconds=error.retry_after),
                colour=colour))

    async def create_and_send_traceback(self, ctx, error):
        error_pages = Paginator()
        lines = traceback.format_exception(type(error), error, error.__traceback__)
        [error_pages.add_line(e) for e in lines]
        if hasattr(self.bot, 'debug') and self.bot.debug:
            for line in error_pages.pages:
                await ctx.send(line)
        else:
            await ctx.send(error)
        error_msg = ""
        if hasattr(ctx.command, 'name'):
            error_msg += f"{ctx.command.name} error:\n"
        error_msg += "\n".join(lines)
        error_msg += f"\nmessage jump url: {ctx.message.jump_url}\n"
        error_msg += f"message content: {ctx.message.content}\n"
        self.logger.error(error_msg)

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
                        f"{ctx.author} used disabled command")
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
                            f"{ctx.author} used disabled command")
        return True

    async def check_for_black_list_user(self, ctx):
        owner_cog = self.bot.get_cog("Owner")
        if owner_cog:
            if ctx.author.id in owner_cog.global_ignores:
                bl_user = ctx.author
                raise BlackListedException(f"blacklisted user: {bl_user} ({bl_user.id}) "
                                           f"tried to use command")
        return True

    async def app_command_error(self, interaction: discord.Interaction, error):
        if not interaction.response.is_done():
            await interaction.response.send_message(content=error, ephemeral=True)
        else:
            await interaction.followup.send(content=error)

async def setup(bot: commands.Bot):
    await bot.add_cog(Default(bot))
