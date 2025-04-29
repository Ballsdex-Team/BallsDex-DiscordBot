# TODO: credits

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

import discord
from discord.ext.commands import Paginator as CommandPaginator

from ballsdex.core.utils import menus

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.core.utils.paginator")


class NumberedPageModal(discord.ui.Modal, title="Go to page"):
    page = discord.ui.TextInput(label="Page", placeholder="Enter a number", min_length=1)

    def __init__(self, max_pages: Optional[int]) -> None:
        super().__init__()
        if max_pages is not None:
            as_string = str(max_pages)
            self.page.placeholder = f"Enter a number between 1 and {as_string}"
            self.page.max_length = len(as_string)

    async def on_submit(self, interaction: discord.Interaction["BallsDexBot"]) -> None:
        self.interaction = interaction
        self.stop()


class Pages(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        *,
        interaction: discord.Interaction["BallsDexBot"],
        check_embeds: bool = False,
        compact: bool = False,
    ):
        super().__init__()
        self.source: menus.PageSource = source
        self.check_embeds: bool = check_embeds
        self.original_interaction = interaction
        self.bot = self.original_interaction.client
        self.current_page: int = 0
        self.compact: bool = compact
        self.clear_items()
        self.fill_items()

    async def send(self, *args, **kwargs):
        if self.original_interaction.response.is_done():
            await self.original_interaction.followup.send(*args, **kwargs)
        else:
            await self.original_interaction.response.send_message(*args, **kwargs)

    def fill_items(self) -> None:
        if not self.compact:
            self.numbered_page.row = 1
            self.stop_pages.row = 1

        if self.source.is_paginating():
            max_pages = self.source.get_max_pages()
            use_last_and_first = max_pages is not None and max_pages >= 2
            if use_last_and_first:
                self.add_item(self.go_to_first_page)
            self.add_item(self.go_to_previous_page)
            if not self.compact:
                self.add_item(self.go_to_current_page)
            self.add_item(self.go_to_next_page)
            if use_last_and_first:
                self.add_item(self.go_to_last_page)
            if not self.compact:
                self.add_item(self.numbered_page)
        self.add_item(self.stop_pages)

    async def _get_kwargs_from_page(self, page: int) -> Dict[str, Any]:
        value = await discord.utils.maybe_coroutine(self.source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}
        elif value is True:
            return {}
        else:
            raise TypeError("Wrong page type returned")

    async def show_page(
        self, interaction: discord.Interaction["BallsDexBot"], page_number: int
    ) -> None:
        page = await self.source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        self._update_labels(page_number)
        if kwargs is not None:
            if interaction.response.is_done():
                await interaction.followup.edit_message(
                    "@original", **kwargs, view=self  # type: ignore
                )
            else:
                await interaction.response.edit_message(**kwargs, view=self)

    def _update_labels(self, page_number: int) -> None:
        self.go_to_first_page.disabled = page_number == 0
        if self.compact:
            max_pages = self.source.get_max_pages()
            self.go_to_last_page.disabled = max_pages is None or (page_number + 1) >= max_pages
            self.go_to_next_page.disabled = (
                max_pages is not None and (page_number + 1) >= max_pages
            )
            self.go_to_previous_page.disabled = page_number == 0
            return

        self.go_to_current_page.label = str(page_number + 1)
        self.go_to_previous_page.label = str(page_number)
        self.go_to_next_page.label = str(page_number + 2)
        self.go_to_next_page.disabled = False
        self.go_to_previous_page.disabled = False
        self.go_to_first_page.disabled = False

        max_pages = self.source.get_max_pages()
        if max_pages is not None:
            self.go_to_last_page.disabled = (page_number + 1) >= max_pages
            if (page_number + 1) >= max_pages:
                self.go_to_next_page.disabled = True
                self.go_to_next_page.label = "…"
            if page_number == 0:
                self.go_to_previous_page.disabled = True
                self.go_to_previous_page.label = "…"

    async def show_checked_page(
        self, interaction: discord.Interaction["BallsDexBot"], page_number: int
    ) -> None:
        max_pages = self.source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(interaction, page_number)
            elif max_pages > page_number >= 0:
                await self.show_page(interaction, page_number)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction[BallsDexBot]) -> bool:
        if not await interaction.client.blacklist_check(interaction):
            return False
        if interaction.user and interaction.user.id in (
            self.bot.owner_id,
            self.original_interaction.user.id,
        ):
            return True
        await interaction.response.send_message(
            "This pagination menu cannot be controlled by you, sorry!", ephemeral=True
        )
        return False

    async def on_timeout(self) -> None:
        self.stop()
        for item in self.children:
            item.disabled = True  # type: ignore
        try:
            await self.original_interaction.followup.edit_message(
                "@original", view=self  # type: ignore
            )
        except discord.HTTPException:
            pass

    async def on_error(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        error: Exception,
        item: discord.ui.Item,
    ) -> None:
        log.error("Error on pagination", exc_info=error)
        if interaction.response.is_done():
            await interaction.followup.send("An unknown error occurred, sorry", ephemeral=True)
        else:
            await interaction.response.send_message(
                "An unknown error occurred, sorry", ephemeral=True
            )

    async def start(self, *, content: Optional[str] = None, ephemeral: bool = False) -> None:
        if (
            self.check_embeds
            and not self.original_interaction.channel.permissions_for(  # type: ignore
                self.original_interaction.guild.me  # type: ignore
            ).embed_links
        ):
            await self.send(
                "Bot does not have embed links permission in this channel.", ephemeral=True
            )
            return

        await self.source._prepare_once()
        page = await self.source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        if content:
            kwargs.setdefault("content", content)

        self._update_labels(0)
        await self.send(**kwargs, view=self, ephemeral=ephemeral)

    @discord.ui.button(label="≪", style=discord.ButtonStyle.grey)
    async def go_to_first_page(
        self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button
    ):
        """go to the first page"""
        await self.show_page(interaction, 0)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.blurple)
    async def go_to_previous_page(
        self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button
    ):
        """go to the previous page"""
        await self.show_checked_page(interaction, self.current_page - 1)

    @discord.ui.button(label="Current", style=discord.ButtonStyle.grey, disabled=True)
    async def go_to_current_page(
        self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button
    ):
        pass

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple)
    async def go_to_next_page(
        self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button
    ):
        """go to the next page"""
        await self.show_checked_page(interaction, self.current_page + 1)

    @discord.ui.button(label="≫", style=discord.ButtonStyle.grey)
    async def go_to_last_page(
        self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button
    ):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(interaction, self.source.get_max_pages() - 1)  # type: ignore

    @discord.ui.button(label="Skip to page...", style=discord.ButtonStyle.grey)
    async def numbered_page(
        self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button
    ):
        """lets you type a page number to go to"""

        modal = NumberedPageModal(self.source.get_max_pages())
        await interaction.response.send_modal(modal)
        timed_out = await modal.wait()

        if timed_out:
            await interaction.followup.send("Took too long", ephemeral=True)
            return
        elif self.is_finished():
            await modal.interaction.response.send_message("Took too long", ephemeral=True)
            return

        value = str(modal.page.value)
        if not value.isdigit():
            await modal.interaction.response.send_message(
                f"Expected a number not {value!r}", ephemeral=True
            )
            return

        value = int(value)
        await self.show_checked_page(modal.interaction, value - 1)
        if not modal.interaction.response.is_done():
            error = modal.page.placeholder.replace("Enter", "Expected")  # type: ignore
            await modal.interaction.response.send_message(error, ephemeral=True)

    @discord.ui.button(label="Quit", style=discord.ButtonStyle.red)
    async def stop_pages(
        self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button
    ):
        """stops the pagination session."""
        for item in self.children:
            item.disabled = True  # type: ignore
        await interaction.response.edit_message(view=self)
        self.stop()


class FieldPageSource(menus.ListPageSource):
    """A page source that requires (field_name, field_value) tuple items."""

    def __init__(
        self,
        entries: list[tuple[Any, Any]],
        *,
        per_page: int = 12,
        inline: bool = False,
        clear_description: bool = True,
    ) -> None:
        super().__init__(entries, per_page=per_page)
        self.embed: discord.Embed = discord.Embed(colour=discord.Colour.blurple())
        self.clear_description: bool = clear_description
        self.inline: bool = inline

    async def format_page(self, menu: Pages, entries: list[tuple[Any, Any]]) -> discord.Embed:
        self.embed.clear_fields()
        if self.clear_description:
            self.embed.description = None

        for key, value in entries:
            self.embed.add_field(name=key, value=value, inline=self.inline)

        maximum = self.get_max_pages()
        if maximum > 1:
            text = f"Page {menu.current_page + 1}/{maximum}"
            self.embed.set_footer(text=text)

        return self.embed


class TextPageSource(menus.ListPageSource):
    def __init__(self, text, *, prefix="```", suffix="```", max_size=2000):
        pages = CommandPaginator(prefix=prefix, suffix=suffix, max_size=max_size - 200)
        for line in text.split("\n"):
            pages.add_line(line)

        super().__init__(entries=pages.pages, per_page=1)

    async def format_page(self, menu: Pages, content):
        maximum = self.get_max_pages()
        if maximum > 1:
            return f"{content}\nPage {menu.current_page + 1}/{maximum}"
        return content


class SimplePageSource(menus.ListPageSource):
    async def format_page(self, menu: SimplePages, entries):
        pages = []
        for index, entry in enumerate(entries, start=menu.current_page * self.per_page):
            pages.append(f"{index + 1}. {entry}")

        maximum = self.get_max_pages()
        if maximum > 1:
            footer = f"Page {menu.current_page + 1}/{maximum}"
            menu.embed.set_footer(text=footer)

        menu.embed.description = "\n".join(pages)
        return menu.embed


class SimplePages(Pages):
    """A simple pagination session reminiscent of the old Pages interface.

    Basically an embed with some normal formatting.
    """

    def __init__(
        self, entries, *, interaction: discord.Interaction["BallsDexBot"], per_page: int = 12
    ):
        super().__init__(SimplePageSource(entries, per_page=per_page), interaction=interaction)
        self.embed = discord.Embed(colour=discord.Colour.blurple())
