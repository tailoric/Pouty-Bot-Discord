from discord.ext import commands
from .utils import checks
import discord
import json
import asyncio

def guild_check(_custom_commands):
    async def predicate(ctx):
        return _custom_commands.get(ctx.command.qualified_name) and ctx.guild.id in _custom_commands.get(ctx.command.qualified_name)
    return commands.check(predicate)

class CustomCommands(commands.Cog):
    """The description for CustomCommands goes here."""

    _custom_commands = {}

    def __init__(self, bot):
        self.bot = bot
        self.init_task = bot.loop.create_task(self.init_database())
        bot.loop.create_task(self.initialize_commands())

    async def init_database(self):
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS custom_command(
                guild_id BIGINT NOT NULL,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                UNIQUE (guild_id, name)
            )
        """)
    async def initialize_commands(self):
        await asyncio.wait_for(self.init_task, timeout=None)
        custom_commands = await self.bot.db.fetch("""
            SELECT * FROM custom_command
        """)
        for command in custom_commands:
            @commands.command(name=command.get("name"), help=f"Custom command: Outputs your custom provided output")
            @guild_check(self._custom_commands)
            async def cmd(self, ctx):
                await ctx.send(self._custom_commands[ctx.invoked_with][ctx.guild.id])

            cmd.cog = self
            # And add it to the cog and the bot
            self.__cog_commands__ = self.__cog_commands__ + (cmd,)
            self.bot.add_command(cmd)
            # Now add it to our list of custom commands
            self._custom_commands[command.get('name')] = {command.get("guild_id"): command.get("content")}
        print(json.dumps(self._custom_commands,indent=2))

    @commands.command(aliases=["addcommand", "addcom"])
    @checks.is_owner_or_moderator()
    async def add_command(self, ctx, name, *, output):
        # First check if there's a custom command with that name already
        existing_command = self._custom_commands.get(name)
        # Check if there's a built in command, we don't want to override that
        if existing_command is None and ctx.bot.get_command(name):
            return await ctx.send(f"A built in command with the name {name} is already registered")

        # Now, if the command already exists then we just need to add/override the message for this guild
        if existing_command:
            self._custom_commands[name][ctx.guild.id] = output
        # Otherwise, we need to create the command object
        else:
            @commands.command(name=name, help=f"Custom command: Outputs your custom provided output")
            @guild_check(self._custom_commands)
            async def cmd(self, ctx):
                await ctx.send(self._custom_commands[ctx.invoked_with][ctx.guild.id])

            cmd.cog = self
            # And add it to the cog and the bot
            self.__cog_commands__ = self.__cog_commands__ + (cmd,)
            ctx.bot.add_command(cmd)
            # Now add it to our list of custom commands
            self._custom_commands[name] = {ctx.guild.id: output}
        await self.bot.db.execute("""
            INSERT INTO custom_command (guild_id, name, content) VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, name) DO UPDATE SET content = $3
        """, ctx.guild.id, name, output)
        await ctx.send(f"Added a command called {name}")

    @commands.command(aliases=["removecom", "rmcom"])
    @checks.is_owner_or_moderator()
    async def remove_command(self, ctx, name):
        # Make sure it's actually a custom command, to avoid removing a real command
        if name not in self._custom_commands or ctx.guild.id not in self._custom_commands[name]:
            return await ctx.send(f"There is no custom command called {name}")
        # All that technically has to be removed, is our guild from the dict for the command
        del self._custom_commands[name][ctx.guild.id]
        if not self._custom_commands[name]:
            del self._custom_commands[name]
            self.bot.remove_command(name)
            await self.bot.db.execute("""
                DELETE FROM custom_command WHERE name=$1
            """, name)
        else:
            await self.bot.db.execute("""
                DELETE FROM custom_command WHERE guild_id=$1 AND name=$2
            """, ctx.guild.id, name)

        await ctx.send(f"Removed a command called {name}")


def setup(bot):
    bot.add_cog(CustomCommands(bot))
