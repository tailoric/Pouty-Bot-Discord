import discord
from discord.ext import commands, menus
import typing

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


class PaginatedView(discord.ui.View):

    def __init__(self, source: menus.PageSource, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._source = source
        self.current_page = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return self.context.author == interaction.user

    @property
    def source(self):
        return self._source

    def should_add_buttons(self):
        return self._source.is_paginating()

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return { 'content': value, 'embed': None }
        elif isinstance(value, discord.Embed):
            return { 'embed': value, 'content': None }

    async def start(self, ctx):
        if not self.should_add_buttons():
            self.clear_items()
        self.context = ctx
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        self.message = await ctx.send(view=self, **kwargs)

    async def show_page(self, page_number):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await self.message.edit(view=self,**kwargs)

    async def show_checked_page(self, page_number):
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    @discord.ui.button(emoji='\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\ufe0f', row=1)
    async def go_to_first_page(self, button: discord.ui.Button, interaction):
        """go to the first page"""
        await self.show_page(0)

    @discord.ui.button(emoji='\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f', row=1)
    async def go_to_previous_page(self, button, interaction):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @discord.ui.button(emoji='\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f', row=1)
    async def go_to_next_page(self, button, interaction):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1)

    @discord.ui.button(emoji='\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\ufe0f', row=1)
    async def go_to_last_page(self, button, interaction):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)

    @discord.ui.button(emoji='\N{BLACK SQUARE FOR STOP}\ufe0f', row=1)
    async def stop_pages(self, button, interaction):
        """stops the pagination session."""
        self.clear_items()
        await self.message.edit(view=self)
        self.stop()
