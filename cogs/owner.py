from typing import Optional
from discord.ext import commands
from discord import User
import discord
from .utils import checks, views
import traceback
import json
import subprocess
import os
import asyncio
import re
import sys
import importlib
import inspect
from pathlib import Path

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
        self.confirmation_reacts = [
            '\N{WHITE HEAVY CHECK MARK}', '\N{CROSS MARK}'
        ]
        self.last_module: Optional[str] = None

    def reload_submodules(self, module, prefix='cogs.'):
        module_self = sys.modules.get(prefix + module)
        members = inspect.getmembers(module_self)
        funclist = [inspect.ismodule, inspect.isfunction, inspect.isclass, inspect.ismethod]
        modules_to_reload = set()
        for member in members:
            module = member[1]
            if any(func(module) for func in funclist) and not inspect.isbuiltin(module):
                try:
                    path = Path(inspect.getfile(module))
                    if 'cogs' in path.parent.name or 'utils' in path.parent.name:
                        modules_to_reload.add(inspect.getmodule(module))
                except TypeError:
                    continue
        utils = inspect.getmembers(sys.modules['cogs.utils'])
        modules_to_reload.update([u[1] for u in utils if any(func(u[1]) for func in funclist)])
        modules_to_reload.discard(module_self)
        for module in modules_to_reload:
            importlib.reload(module)

    @commands.command(name="sync", aliases=["rlslash"])
    @checks.is_owner()
    async def reload_slash(self, ctx: commands.Context, sync_context: str="*"):
        if sync_context == "~":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            await ctx.bot.tree.sync(guild=ctx.guild)
            await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")
        elif sync_context == "*":
            await ctx.bot.tree.sync()
            await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")
        else:
            await ctx.send("invalid context provided for sync")

    #
    #
    # loading and unloading command by Rapptz
    #       https://github.com/Rapptz/
    #
    @commands.command(hidden=True)
    @checks.is_owner_or_moderator()
    async def load(self, ctx, module: str, with_prefix=True):
        """Loads a module"""
        self.last_module = module
        try:
            if with_prefix:
                self.reload_submodules(module)
                module = 'cogs.'+ module
            await self.bot.load_extension(module)
        except Exception as e:
            await ctx.send('\N{THUMBS DOWN SIGN}')
            paginator = commands.Paginator()
            trace = traceback.format_exc()
            trace = trace.split("\n")
            for line in trace:
                paginator.add_line(line)
            for page in paginator.pages:
                await ctx.send(page)
        else:
            await ctx.send('\N{THUMBS UP SIGN}')
            if module != "cogs.default":
                await self.bot.db.execute("""
                INSERT INTO cogs VALUES ($1) ON CONFLICT DO NOTHING;
                """, module)

    @commands.command(hidden=True)
    @checks.is_owner_or_moderator()
    async def unload(self, ctx, module:str, with_prefix=True):
        """Unloads a module"""
        if module == "owner" or module == "default":
            await ctx.send("This cog cannot be unloaded")
            return
        try:
            if with_prefix:
                module = 'cogs.'+module
            await self.bot.unload_extension(module)
        except Exception as e:
            await ctx.send('\N{THUMBS DOWN SIGN}')
            await ctx.send('`{}: {}`'.format(type(e).__name__, e))
        else:
            await ctx.send('\N{THUMBS UP SIGN}')
            await self.bot.db.execute("""
            DELETE FROM cogs WHERE module = $1
            """, module)
    @commands.command(name='reload', hidden=True, aliases=["rl"])
    @checks.is_owner_or_moderator()
    async def _reload(self, ctx, module : Optional[str], with_prefix=True):
        """Reloads a module."""
        if module:
            self.last_module = module
        elif not (module or self.last_module):
            return await ctx.send("please provide a module to load, I currently don't have the last module stored")
        else:
            module = self.last_module
        try:
            if with_prefix:
                self.reload_submodules(module)
                if module:
                    module = 'cogs.' + module
                await self.bot.reload_extension(module)
            else:
                await self.bot.reload_extension(module)
        except Exception as e:
            try:
                await self.bot.load_extension(module)
                self.reload_submodules(module)
                await ctx.send(f'loaded `{module}` \N{THUMBS UP SIGN}')
                if module != "cogs.default":
                    await self.bot.db.execute("""
                    INSERT INTO cogs VALUES ($1) ON CONFLICT DO NOTHING;
                    """, module)
            except Exception as inner_e:
                await ctx.send('\N{THUMBS DOWN SIGN}')

                paginator = commands.Paginator()
                trace = traceback.format_exc()
                trace = trace.split("\n")
                for line in trace:
                    paginator.add_line(line)
                for page in paginator.pages:
                    await ctx.send(page)
        else:
            await ctx.send(f'reloaded `{module}` \N{THUMBS UP SIGN}')

    @commands.command(name='shutdown', hidden=True)
    @checks.is_owner_or_admin()
    async def _shutdown(self, ctx):
        """Shutdown bot"""
        await self.bot.db.executemany("""
        INSERT INTO cogs VALUES ($1) ON CONFLICT DO NOTHING;
        """, [(k,) for k in self.bot.extensions.keys() if k != "cogs.default"])
        await ctx.send('Shutting down...')
        await self.bot.close()

    @commands.group(pass_context=True, aliases=['bl'])
    @checks.is_owner_or_moderator()
    async def blacklist(self, ctx):
        """
        Blacklist management commands
        :return:
        """
        if ctx.invoked_subcommand is None:
            await ctx.send("use `blacklist add` or `global_ignores remove`")

    async def run_process(self, command):
        try:
            process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result = await process.communicate()
        except NotImplementedError:
            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result = await self.bot.loop.run_in_executor(None, process.communicate)

        return [output.decode() for output in result]

    _GIT_PULL_REGEX = re.compile(r'\s*(?P<filename>.+?)\s*\|\s*[0-9]+\s*[+-]+')

    def find_modules_from_git(self, output):
        files = self._GIT_PULL_REGEX.findall(output)
        ret = []
        for file in files:
            root, ext = os.path.splitext(file)
            if ext != '.py':
                continue

            if root.startswith('cogs/'):
                # A submodule is a directory inside the main cog directory for
                # my purposes
                ret.append((root.count('/') - 1, root.replace('/', '.')))

        # For reload order, the submodules should be reloaded first
        ret.sort(reverse=True)
        return ret

    async def reload_or_load_extension(self, module):
        try:
            await self.bot.reload_extension(module)
        except commands.ExtensionNotLoaded:
            await self.bot.load_extension(module)
            if module != "cogs.default":
                await self.bot.db.execute("""
                INSERT INTO cogs VALUES ($1) ON CONFLICT DO NOTHING;
                """, module)

    @commands.command()
    @commands.is_owner()
    async def update(self, ctx):
        """Reloads all modules, while pulling from git."""

        async with ctx.typing():
            stdout, stderr = await self.run_process('git pull')

        # progress and stuff is redirected to stderr in git pull
        # however, things like "fast forward" and files
        # along with the text "already up-to-date" are in stdout

        if stdout.startswith('Already up-to-date.'):
            return await ctx.send(stdout)

        modules = self.find_modules_from_git(stdout)
        mods_text = '\n'.join(f'{index}. `{module}`' for index, (_, module) in enumerate(modules, start=1))
        prompt_text = f'This will update the following modules, are you sure?\n{mods_text}'
        confirm = views.Confirm(ctx)
        mes = await ctx.send(prompt_text, view=confirm)
        await confirm.wait()
        if not confirm.is_confirmed:
            return
        statuses = []
        for is_submodule, module in modules:
            if is_submodule:
                try:
                    actual_module = sys.modules[module]
                except KeyError:
                    statuses.append((ctx.tick(None), module))
                else:
                    try:
                        importlib.reload(actual_module)
                    except Exception as e:
                        statuses.append((self.confirmation_reacts[1], module))
                    else:
                        statuses.append((self.confirmation_reacts[0], module))
            else:
                try:
                    await self.reload_or_load_extension(module)
                except commands.ExtensionError:
                    statuses.append((self.confirmation_reacts[1], module))
                else:
                    statuses.append((self.confirmation_reacts[0], module))

        await ctx.send('\n'.join(f'{status}: `{module}`' for status, module in statuses))



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
        await ctx.send("command {} enabled".format(command))

async def setup(bot):
    await bot.add_cog(Owner(bot))
