import discord
from discord.ext import commands, menus
import typing

class Confirm(discord.ui.View):
    def __init__(self, user: typing.Union[discord.Member, discord.User], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.is_confirmed = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user is not None and self.user.id == interaction.user.id

    async def on_timeout(self) -> None:
        self.is_confirmed = False

    @discord.ui.button(emoji="\N{WHITE HEAVY CHECK MARK}", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.is_confirmed = True
        self.clear_items()
        self.stop()
        await interaction.response.edit_message(view=self)


    @discord.ui.button(emoji="\N{HEAVY MULTIPLICATION X}", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.is_confirmed = False
        self.clear_items()
        self.stop()
        await interaction.response.edit_message(view=self)


class PaginatedView(discord.ui.View):

    def __init__(self, source: menus.PageSource, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._source = source
        self.current_page = 0
        self.interaction = None

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
        if self.interaction:
            await self.interaction.response.edit_message(view=self, **kwargs)
        else:
            await self.message.edit(view=self,**kwargs)

    async def show_checked_page(self, page_number):
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number)
            else:
                await self.show_page(self.current_page)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            print("index error")
            await self.show_page(self.current_page)

    @discord.ui.button(emoji='\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\ufe0f', row=1)
    async def go_to_first_page(self, interaction, button: discord.ui.Button):
        """go to the first page"""
        self.interaction = interaction
        await self.show_page(0)

    @discord.ui.button(emoji='\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f', row=1)
    async def go_to_previous_page(self, interaction, button):
        """go to the previous page"""
        self.interaction = interaction
        await self.show_checked_page(self.current_page - 1)

    @discord.ui.button(emoji='\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f', row=1)
    async def go_to_next_page(self, interaction, button):
        """go to the next page"""
        self.interaction = interaction
        await self.show_checked_page(self.current_page + 1)

    @discord.ui.button(emoji='\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\ufe0f', row=1)
    async def go_to_last_page(self, interaction, button):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        self.interaction = interaction
        await self.show_page(self._source.get_max_pages() - 1)

    @discord.ui.button(emoji='\N{BLACK SQUARE FOR STOP}\ufe0f', row=1)
    async def stop_pages(self, interaction, button):
        """stops the pagination session."""
        self.clear_items()
        await self.message.edit(view=self)
        self.stop()
