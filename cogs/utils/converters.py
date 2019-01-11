from discord.ext import commands
from discord.utils import find

class RoleConverter(commands.Converter):


    async def convert(self):
        server = self.ctx.message.server
        return find(lambda r: r.name.lower() == self.argument, server.roles)
