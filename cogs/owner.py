from discord.ext import commands
from discord import User
from .utils import checks
from bot import shutdown
import json
import os

class Owner:
    def __init__(self, bot):
        self.bot = bot
        if os.path.exists("data/ignores.json"):
            with open("data/ignores.json") as f:
                self.global_ignores = json.load(f)
        else:
            self.global_ignores = []


    #
    #
    # loading and unloading command by Rapptz
    #       https://github.com/Rapptz/
    #
    @commands.command(hidden=True)
    @checks.is_owner_or_moderator()
    async def load(self, *, module: str):
        """Loads a module"""
        try:
            self.bot.load_extension('cogs.'+module)
        except Exception as e:
            await self.bot.say('\N{THUMBS DOWN SIGN}')
            await self.bot.say('`{}: {}`'.format(type(e).__name__, e))
        else:
            await self.bot.say('\N{THUMBS UP SIGN}')

    @commands.command(hidden=True)
    @checks.is_owner_or_moderator()
    async def unload(self, *, module:str):
        """Unloads a module"""
        try:
            self.bot.unload_extension('cogs.'+module)
        except Exception as e:
            await self.bot.say('\N{THUMBS DOWN SIGN}')
            await self.bot.say('`{}: {}`'.format(type(e).__name__, e))
        else:
            await self.bot.say('\N{THUMBS UP SIGN}')

    @commands.command(name='reload', hidden=True)
    @checks.is_owner_or_moderator()
    async def _reload(self, *, module : str):
        """Reloads a module."""
        try:
            self.bot.unload_extension('cogs.'+module)
            self.bot.load_extension('cogs.'+module)
        except Exception as e:
            await self.bot.say('\N{THUMBS DOWN SIGN}')
            await self.bot.say('{}: {}'.format(type(e).__name__, e))
        else:
            await self.bot.say('\N{THUMBS UP SIGN}')

    @commands.command(name='shutdown', hidden=True)
    @checks.is_owner_or_admin()
    async def _shutdown(self):
        """Shutdown bot"""
        try:
            await self.bot.say('Shutting down...')
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
            await self.bot.say("use `blacklist add` or `global_ignores remove`")

    @blacklist.command(name="add", pass_context=True)
    async def _blacklist_add(self, ctx, user: User):
        if ctx.message.author.id == user.id:
            await self.bot.say("Don't blacklist yourself, dummy")
            return
        if user.id not in self.global_ignores:
            self.global_ignores.append(user.id)
            with open("data/ignores.json", "w") as f:
                json.dump(self.global_ignores,f)
            await self.bot.say('User {} has been blacklisted'.format(user.name))
        else:
            await self.bot.say("User {} already is blacklisted".format(user.name))


    @blacklist.command(name="remove")
    async def _blacklist_remove(self, user:User):
        if user.id in self.global_ignores:
            self.global_ignores.remove(user.id)
            with open("data/ignores.json", "w") as f:
                json.dump(self.global_ignores, f)
            await self.bot.say("User {} has been removed from blacklist".format(user.name))
        else:
            await self.bot.say("User {} is not blacklisted".format(user.name))
def setup(bot):
    bot.add_cog(Owner(bot))
