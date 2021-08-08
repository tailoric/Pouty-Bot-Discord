import discord
from discord.ext import commands

class Confirm(discord.ui.View):
    def __init__(self, ctx: commands.Context, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.context = ctx
        self.is_confirmed = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user is not None and self.context.author.id == interaction.user.id

    async def on_timeout(self) -> None:
        self.is_confirmed = False

    @discord.ui.button(emoji="\N{WHITE HEAVY CHECK MARK}", style=discord.ButtonStyle.primary)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.is_confirmed = True
        self.clear_items()
        self.stop()
        await interaction.response.edit_message(view=self)


    @discord.ui.button(emoji="\N{CROSS MARK}", style=discord.ButtonStyle.danger)
    async def deny(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.is_confirmed = False
        self.clear_items()
        self.stop()
        await interaction.response.edit_message(view=self)

