import discord
import re
from textwrap import shorten
from discord.ext import commands


class MessageLink(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def create_embed(author: discord.User, message: discord.Message):
        if isinstance(message.channel, discord.Thread) and message.channel.is_private():
            message.content = message.content.replace("||", "")
            message.content = f"possibly spoilers for ({message.channel.name}) || {message.content} ||"
        embed = discord.Embed(description=shorten(
            message.content, width=2000), colour=message.author.colour)
        embed.set_author(name=message.author.display_name,
                         icon_url=message.author.display_avatar.replace(format="png"))
        if message.reference and message.reference.resolved:
            replied_to = message.reference.resolved
            if isinstance(replied_to, discord.Message):
                content = replied_to.content
                match = re.search(r'\|\|\s?\w+\s?\|\|', content)
                if match:
                    content = ""
                embed.add_field(
                    name=f"Reply to {replied_to.author}", value=f"[{shorten(content, 50) or 'click to view'}]({replied_to.jump_url})", inline=False)
        if message.attachments:
            file = message.attachments[0]
            spoiler = file.is_spoiler()
            is_nsfw = message.channel.is_nsfw()
            if not spoiler and not is_nsfw and not isinstance(message.channel, discord.Thread) and file.url.lower().endswith(('png', 'jpg', 'jpeg', 'gif', 'webp')):
                embed.set_image(url=file.url)
            elif (spoiler and not is_nsfw) or isinstance(message.channel, discord.Thread):
                embed.add_field(
                    name="Attachment", value=f"|| [{file.filename}]({file.url}) ||", inline=False)
            elif is_nsfw:
                embed.add_field(
                    name="Attachment", value=f"[**(NSFW)** {file.filename}]({file.url})", inline=False)
            else:
                embed.add_field(
                    name="Attachment", value=f"[{file.filename}]({file.url})", inline=False)
        embed.add_field(name="Channel", value=message.channel.mention)
        embed.set_footer(text=f"Linked by {author.display_name}",
                         icon_url=author.display_avatar.replace(format="png"))
        return embed

    @commands.command(name="link")
    async def message_link(self, ctx: commands.Context, link: discord.Message):
        # Creating a button that the user can click on to jump to the original message.
        jump_view = discord.ui.View(timeout=None)
        jump_button = discord.ui.Button(label="Jump!", url=link.jump_url)
        jump_view.add_item(jump_button)
        await ctx.send(embed=await MessageLink.create_embed(ctx.author, link), view=jump_view)
        await ctx.message.delete()


async def setup(bot: commands.Bot):
    await bot.add_cog(MessageLink(bot))
