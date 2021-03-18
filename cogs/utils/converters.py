from discord.ext import commands
from discord.utils import find
from discord.ext.commands.errors import BadArgument
from discord import Message


class RoleConverter(commands.Converter):

    async def convert(self, ctx, argument):
        server = ctx.message.guild
        role = find(lambda r: r.name.lower() == argument.lower(), server.roles)
        if role is None:
            raise BadArgument('Role {} not found'.format(argument))
        return role

class ReferenceDeleted(commands.BadArgument):
    pass
class ReferenceNotFound(commands.BadArgument):
    pass
class ReferenceOrMessage(commands.MessageConverter):
    @classmethod
    async def convert(self, ctx, argument):
        """
        Try to fetch the referenced message (reply) from command invocation.
        If a reference exists try best effort to fetch that message, otherwise
        raise an Error.
        If command invocation has no reference try to fetch the message provided
        in the argument instead.

        Raises
        ------
        `ChannelNotFound`, `MessageNotFound` or `ChannelNotFound` if trying to convert argument

        `ReferenceDeleted` if the reference doesn't exist anymore
        `ReferenceNotFound` if the reference was not found
        """
        referenced = ctx.message.reference
        if referenced and referenced.resolved:
            if isinstance(referenced.resolved, Message):
                return referenced.resolved
            else:
                raise ReferenceDeleted("The replied message was deleted.")
        elif referenced and referenced.message_id and not reference.resolved:
            message = await ctx.channel.fetch_message(referenced.message_id)
            if message:
                return message
            else:
                raise ReferenceNotFound("I was unable to fetch the replied message.")
        else:
            await super().convert(ctx, argument)



