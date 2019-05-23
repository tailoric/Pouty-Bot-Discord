from discord.ext import commands


class DisabledCommandException(commands.CheckFailure):
    pass
