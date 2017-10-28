from discord.ext import commands
from .utils import checks
from bot import shutdown
import sys

class Owner:
    def __init__(self, bot):
        self.bot = bot
    #
    #
    # loading and unloading command by Rapptz
    #       https://github.com/Rapptz/
    #
    @commands.command(hidden=True)
    @checks.is_owner()
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
    @checks.is_owner()
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
    @checks.is_owner()
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
    @checks.is_owner()
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
    @commands.command(name='error', hidden=True)
    @checks.is_owner()
    async def _error(self):
        sys.exit(1)

def setup(bot):
    bot.add_cog(Owner(bot))
