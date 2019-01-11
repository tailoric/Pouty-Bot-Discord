from discord.ext import commands
from discord.utils import find
from discord.ext.commands.errors import BadArgument


class RoleConverter(commands.Converter):

    async def convert(self):
        server = self.ctx.message.server
        role = find(lambda r: r.name.lower() == self.argument, server.roles)
        if role is None:
            raise BadArgument('Role {} not found'.format(self.argument))
        return role
