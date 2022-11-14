import discord
import re
from textwrap import shorten
from discord.ext import commands


class JumpView(discord.ui.View):
    def __init__(self, message: discord.Message):
        super().__init__(timeout=None)
        self.message = message
        jump_button = discord.ui.Button(label="Jump!", url=message.jump_url)
        self.add_item(jump_button)

    def create_embed(self, author: discord.User):
        """Creates an embed for the message that was linked by the user."""
        msg = self.message
        # Spoiler thread handling.
        if isinstance(msg.channel, discord.Thread) and msg.channel.is_private():
            msg.content = msg.content.replace("||", "")
            msg.content = f"possibly spoilers for ({msg.channel.name}) || {msg.content} ||"
        # Setting the colour of the message to the role colour of the user.
        embed = discord.Embed(description=shorten(
            msg.content, width=2000), colour=msg.author.colour)
        # Author is the linked messages author.
        embed.set_author(name=msg.author.display_name,
                         icon_url=msg.author.display_avatar.replace(format="png"))
        # Handling replies, creates a new button for jumping to replied messages.
        if msg.reference and msg.reference.resolved:
            replied_to = msg.reference.resolved
            if isinstance(replied_to, discord.Message):
                content = replied_to.content
                match = re.search(r'\|\|\s?\w+\s?\|\|', content)
                if match:
                    content = ""
                embed.add_field(
                    name=f"Reply to {replied_to.author}", value=f"{shorten(content, 50) or 'Jump to view content.'}", inline=False)
                reply_button = discord.ui.Button(
                    label="Replied Message", url=replied_to.jump_url)
                self.add_item(reply_button)
        # Handling images, only handles singular images at a time.
        if msg.attachments:
            file = msg.attachments[0]
            spoiler = file.is_spoiler()
            is_nsfw = msg.channel.is_nsfw()
            if not spoiler and not is_nsfw and not isinstance(msg.channel, discord.Thread) and file.url.lower().endswith(('png', 'jpg', 'jpeg', 'gif', 'webp')):
                embed.set_image(url=file.url)
            elif (spoiler and not is_nsfw) or isinstance(msg.channel, discord.Thread):
                embed.add_field(
                    name="Attachment", value=f"|| [{file.filename}]({file.url}) ||", inline=False)
            elif is_nsfw:
                embed.add_field(
                    name="Attachment", value=f"[**(NSFW)** {file.filename}]({file.url})", inline=False)
            else:
                embed.add_field(
                    name="Attachment", value=f"[{file.filename}]({file.url})", inline=False)
        embed.add_field(name="Channel", value=msg.channel.mention)
        embed.add_field(name="Posted",
                        value=discord.utils.format_dt(msg.created_at, style='R'))
        # The footer is the person who linked the message.
        embed.set_footer(text=f"Linked by {author.display_name}",
                         icon_url=author.display_avatar.replace(format="png"))
        return embed


class MessageLink(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener('on_message')
    async def link_message(self, message: discord.Message):
        """Command for embedding a linked message."""
        if message.author == self.bot.user:
            return
        # Checking if the message sent is a link to a discord message.
        id_regex = re.compile(
            r'(?:(?P<channel_id>[0-9]{15,20})-)?(?P<message_id>[0-9]{15,20})$')
        link_regex = re.compile(
            r'https?://(?:(ptb|canary|www)\.)?discord(?:app)?\.com/channels/'
            r'(?P<guild_id>[0-9]{15,20}|@me)'
            r'/(?P<channel_id>[0-9]{15,20})/(?P<message_id>[0-9]{15,20})/?$'
        )
        match = link_regex.match(
            message.content) or id_regex.match(message.content)
        # If it's not a message link, we simply return.
        if not match:
            return
        # Parsing out the channel ID and message ID from the regular expression.
        data = match.groupdict()
        channel_id, message_id = int(data['channel_id']), int(data['message_id'])
        linked_channel = self.bot.get_channel(channel_id)
        partial_linked_message = linked_channel.get_partial_message(message_id)
        # Fetching the full message.
        linked_message = await partial_linked_message.fetch()
        # Constructing the embed, and then deleting the original
        jump_view = JumpView(linked_message)
        await message.channel.send(embed=jump_view.create_embed(message.author), view=jump_view)
        # Only deleting if this is within a server, rather than a DM channel.
        if message.guild:
            await message.delete()


async def setup(bot: commands.Bot):
    await bot.add_cog(MessageLink(bot))
