import discord
from discord.ext import commands
from discord import app_commands
from discord import ui
import textwrap
import logging 

logger = logging.getLogger('report')

class ReportUserForm(ui.Modal, title="Report User"):
    message = ui.TextInput(label="Report Message", style=discord.TextStyle.paragraph, placeholder="Write the report reason in here.", max_length=2500)

    
    user: discord.Member

    def __init__(self, bot, user, reporter):
        self.bot : commands.Bot = bot
        self.user : discord.Member = user
        self.title=f"Report {user.display_name}"
        self.admin = self.bot.get_cog("Admin")
        self.reporter = reporter
        super().__init__()

    @property
    def embed(self):
        embed = discord.Embed(title="User Report", description=self.message)
        embed.add_field(name="Username", value=self.user.display_name)
        embed.add_field(name="User ID", value=self.user.id)
        embed.add_field(name="Join Date", value=discord.utils.format_dt(self.user.joined_at))
        embed.add_field(name="Mention", value=self.user.mention)
        embed.set_thumbnail(url=self.user.display_avatar)
        if last_msg := next(filter(lambda m: m.guild == self.user.guild and m.author == self.user, reversed(self.bot.cached_messages)), None):
            embed.add_field(name="Last Message", value=last_msg.jump_url, inline=False)
        return embed

    async def on_submit(self, interaction: discord.Interaction):
        if self.admin and self.admin.report_channel:
            try:
                await self.admin.report_channel.send(embed=self.embed)
                await interaction.response.send_message(content="Report sent", ephemeral=True)
                logger.info('User %s#%s(id:%s) reported: "%s"', self.reporter.name, self.reporter.discriminator, self.reporter.id, self.message)
            except Exception as e:
                await interaction.response.send_message(content="Sending report failed unexpectedly", ephemeral=True)
                raise e
        else:
            await interaction.response.send_message(content="Report channel not set up", ephemeral=True)

class ReportMessageForm(ui.Modal, title="Report Message Content"):
    report = ui.TextInput(label="Report Message", style=discord.TextStyle.paragraph, placeholder="Write the report reason in here.", max_length=1024)

    message: discord.Message

    def __init__(self, bot, message, reporter):
        self.bot = bot
        self.message = message
        self.admin = self.bot.get_cog("Admin")
        self.reporter = reporter
        super().__init__()

    @property
    def embed(self):
        embed = discord.Embed(title="Message Report", description=textwrap.shorten(self.message.content, width=2000))
        embed.add_field(name="Author", value=self.message.author.mention)
        embed.add_field(name="Channel", value=self.message.channel.mention)
        embed.add_field(name="Report Reason", value=self.report, inline=False)
        embed.add_field(name="Message URL", value=self.message.jump_url, inline=False)
        embed.set_thumbnail(url=self.message.author.display_avatar)
        if self.message.attachments:
            embed.set_image(url=self.message.attachments[0])
        return embed

    async def on_submit(self, interaction: discord.Interaction):
        if self.admin and self.admin.report_channel:
            try:
                await self.admin.report_channel.send(embed=self.embed)
                await interaction.response.send_message(content="Report sent", ephemeral=True)
                logger.info('User %s#%s(id:%s) reported: "%s"', self.reporter.name, self.reporter.discriminator, self.reporter.id, self.report)
            except Exception as e:
                await interaction.response.send_message(content="Sending report failed unexpectedly", ephemeral=True)
                raise e
        else:
            await interaction.response.send_message(content="Report channel not set up", ephemeral=True)


async def commands_sync(bot: commands.Bot, tree: app_commands.CommandTree):
    for guild in bot.guilds:
        await tree.sync(guild=guild)
    await tree.sync()

def setup(bot: commands.Bot):

    @bot.tree.context_menu(name="Report User", guilds=bot.guilds)
    async def report_user(interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_modal(ReportUserForm(bot,member, interaction.user))


    @bot.tree.context_menu(name="Report Message", guilds=bot.guilds)
    async def report_message(interaction: discord.Interaction, message: discord.Message):
        await interaction.response.send_modal(ReportMessageForm(bot,message, interaction.user))

    bot.loop.create_task(commands_sync(bot, bot.tree))

def teardown(bot: commands.Bot):
    for guild in bot.guilds:
        bot.tree.remove_command("Report User", guild=guild, type=discord.AppCommandType.user)
        bot.tree.remove_command("Report Message", guild=guild, type=discord.AppCommandType.message)

    bot.tree.remove_command("Report User", type=discord.AppCommandType.user)
    bot.tree.remove_command("Report Message", type=discord.AppCommandType.message)
    bot.loop.create_task(commands_sync(bot, bot.tree))
