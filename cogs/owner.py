from discord.ext import commands
from discord import User
from .utils import checks
from bot import shutdown
import json
import os

class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if os.path.exists("data/ignores.json"):
            with open("data/ignores.json") as f:
                self.global_ignores = json.load(f)
        else:
            self.global_ignores = []
        if os.path.exists("data/disabled_commands.json"):
            with open('data/disabled_commands.json') as f:
                self.disabled_commands = json.load(f)
        else:
            self.disabled_commands = []
        self.disabled_commands_file = 'data/disabled_commands.json'


    #
    #
    # loading and unloading command by Rapptz
    #       https://github.com/Rapptz/
    #
    @commands.command(hidden=True)
    @checks.is_owner_or_moderator()
    async def load(self, ctx, *, module: str):
        """Loads a module"""
        try:
            self.bot.load_extension('cogs.'+module)
        except Exception as e:
            await ctx.send('\N{THUMBS DOWN SIGN}')
            await ctx.send('`{}: {}`'.format(type(e).__name__, e))
        else:
            await ctx.send('\N{THUMBS UP SIGN}')

    @commands.command(hidden=True)
    @checks.is_owner_or_moderator()
    async def unload(self, ctx, *, module:str):
        """Unloads a module"""
        try:
            self.bot.unload_extension('cogs.'+module)
        except Exception as e:
            await ctx.send('\N{THUMBS DOWN SIGN}')
            await ctx.send('`{}: {}`'.format(type(e).__name__, e))
        else:
            await ctx.send('\N{THUMBS UP SIGN}')

    @commands.command(name='reload', hidden=True)
    @checks.is_owner_or_moderator()
    async def _reload(self, ctx, *, module : str):
        """Reloads a module."""
        try:
            self.bot.reload_extension('cogs.'+module)
        except Exception as e:
            try:
                self.bot.load_extension('cogs.'+module)
                await ctx.send('\N{THUMBS UP SIGN}')
            except Exception as inner_e:
                await ctx.send('\N{THUMBS DOWN SIGN}')
                await ctx.send('{}: {}'.format(type(e).__name__, e))
        else:
            await ctx.send('\N{THUMBS UP SIGN}')

    @commands.command(name='shutdown', hidden=True)
    @checks.is_owner_or_admin()
    async def _shutdown(self, ctx):
        """Shutdown bot"""
        try:
            await ctx.send('Shutting down...')
        except:
            pass
        extensions = self.bot.extensions.copy()
        for extension in extensions:
            self.bot.unload_extension(extension)
        await shutdown(bot=self.bot)

    @commands.group(pass_context=True, aliases=['bl'])
    @checks.is_owner_or_moderator()
    async def blacklist(self, ctx):
        """
        Blacklist management commands
        :return:
        """
        if ctx.invoked_subcommand is None:
            await ctx.send("use `blacklist add` or `global_ignores remove`")

    @blacklist.command(name="add", pass_context=True)
    async def _blacklist_add(self, ctx, user: User):
        if ctx.message.author.id == user.id:
            await ctx.send("Don't blacklist yourself, dummy")
            return
        if user.id not in self.global_ignores:
            self.global_ignores.append(user.id)
            with open("data/ignores.json", "w") as f:
                json.dump(self.global_ignores,f)
            await ctx.send('User {} has been blacklisted'.format(user.name))
        else:
            await ctx.send("User {} already is blacklisted".format(user.name))


    @blacklist.command(name="remove")
    async def _blacklist_remove(self, ctx, user:User):
        if user.id in self.global_ignores:
            self.global_ignores.remove(user.id)
            with open("data/ignores.json", "w") as f:
                json.dump(self.global_ignores, f)
            await ctx.send("User {} has been removed from blacklist".format(user.name))
        else:
            await ctx.send("User {} is not blacklisted".format(user.name))

    @commands.group(name="command", pass_context=True)
    @checks.is_owner()
    async def _commands(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("use `command help`")

    @_commands.command(name='disable', pass_context=True)
    async def _commands_disable(self, ctx, command:str ):
        server = ctx.message.guild
        self.disabled_commands.append({"server": server.id, "command": command})
        with open(self.disabled_commands_file, 'w') as f:
            json.dump(self.disabled_commands, f)
        await ctx.send("command {} disabled".format(command))

    @_commands.command(name='enable', pass_context=True)
    async def _commands_enable(self, ctx, command:str ):
        server = ctx.message.guild
        self.disabled_commands.remove({"server": server.id, "command": command})
        with open(self.disabled_commands_file, 'w') as f:
            json.dump(self.disabled_commands, f)
        await self.bot.say("command {} enabled".format(command))
def setup(bot):
    bot.add_cog(Owner(bot))
