import discord
from discord.ext import commands
import traceback
import typing
from aiohttp import ClientSession
import io
import logging

class SpoilerArg(commands.Converter):

    async def convert(self, ctx, argument):
        match = re.match(r"\((.+?)\)\s?\|\|(.+?)\|\|",argument)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        else:
            raise commands.BadArgument("Could not format spoiler input format is `(source)||phrase||`", argument)

class NotUrlError(commands.CheckFailure):
    pass

class SimpleUrlArg(commands.Converter):
    async def convert(self, ctx, argument):
        if not argument.startswith(("http", "https")):
            raise NotUrlError("First argument was not an URL.")
        else:
            return argument

class SpoilerCheck(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = ClientSession()
        self.logger = logging.getLogger("PoutyBot")


    missing_source : str = ("Please provide what this is spoiling"
            " or give a NSFW or Content Warning after the link."
            " (or in the input field of the file upload)")

    @commands.command(name="spoiler")
    @commands.guild_only()
    async def spoiler(self, ctx, link: typing.Optional[SimpleUrlArg], * , source):
        """
        command for reuploading an image or file spoiler tagged (for mobile users)
        """
        filename = None
        if not link and ctx.message.attachments:
            attachment: discord.Attachment = ctx.message.attachments[0]
            link = attachment.url
            filename = attachment.filename
        await ctx.message.delete()
        if not link and not ctx.message.attachments:
            return await ctx.send("There was no file attached to this message")
        async with self.session.get(url=link) as resp:
            resp.raise_for_status()
            if not filename:
                filename = link.rsplit("/")[-1]
            byio = io.BytesIO(await resp.read())           
            await ctx.send(content=f"File spoiler tagged for user {ctx.author.mention}\nSpoiler/Content Warning: **[{source}]**",
                    file=discord.File(fp=byio, filename=filename, spoiler=True),
                    allowed_mentions=discord.AllowedMentions.none())



    @spoiler.error
    async def spoiler_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument) and error.param.name == "source":
            await ctx.message.delete()
            await ctx.send(self.missing_source)
            error = None
        elif isinstance(error, commands.CheckAnyFailure):
            return
        else:
            error_pages = commands.Paginator()
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
    

def setup(bot):
    bot.add_cog(SpoilerCheck(bot))
