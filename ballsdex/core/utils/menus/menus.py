from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from discord.ui import ActionRow, Button, LayoutView, button

from ballsdex.core.discord import Modal

from .formatter import CountryballFormatter
from .source import ModelSource

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot
    from bd_models.models import BallInstance

    from .formatter import Formatter
    from .source import Source

type Interaction = discord.Interaction["BallsDexBot"]


class NumberedPageModal(Modal, title="Go to page"):
    page = discord.ui.TextInput(label="Page", placeholder="Enter a number", min_length=1)

    def __init__(self, menu: Menu):
        super().__init__()
        self.menu = menu
        as_string = str(menu.source.get_max_pages())
        self.page.placeholder = f"Enter a number between 1 and {as_string}"
        self.page.max_length = len(as_string)

    async def on_submit(self, interaction: Interaction):
        try:
            page = int(self.page.value)
        except ValueError:
            await interaction.response.send_message("Expected a number", ephemeral=True)
        else:
            if page < 1:
                await interaction.response.send_message("Minimum value is 1", ephemeral=True)
            elif page > (max := self.menu.source.get_max_pages()):
                await interaction.response.send_message(f"Maximum value is {max}", ephemeral=True)
            else:
                await self.menu.show_page(interaction, page - 1)


class Controls(ActionRow):
    def __init__(self, menu: Menu):
        super().__init__()
        self.menu = menu

    @button(label="≪", style=discord.ButtonStyle.grey)
    async def go_to_first_page(self, interaction: Interaction, button: Button):
        await self.menu.show_page(interaction, 0)

    @button(label="Back", style=discord.ButtonStyle.blurple)
    async def go_to_previous_page(self, interaction: Interaction, button: Button):
        await self.menu.show_page(interaction, self.menu.current_page - 1)

    @button(label="1 (go to)", style=discord.ButtonStyle.blurple)
    async def go_to_page(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(NumberedPageModal(self.menu))

    @button(label="Next", style=discord.ButtonStyle.blurple)
    async def go_to_next_page(self, interaction: Interaction, button: Button):
        await self.menu.show_page(interaction, self.menu.current_page + 1)

    @button(label="≫", style=discord.ButtonStyle.grey)
    async def go_to_last_page(self, interaction: Interaction, button: Button):
        await self.menu.show_page(interaction, self.menu.source.get_max_pages() - 1)

    def edit_buttons(self, page: int):
        max = self.menu.source.get_max_pages()
        self.go_to_page.label = f"{str(page + 1)} (go to)"
        if page > 0:
            self.go_to_previous_page.label = str(page)
            self.go_to_previous_page.disabled = False
            self.go_to_first_page.disabled = False
        else:
            self.go_to_previous_page.label = "Back"
            self.go_to_previous_page.disabled = True
            self.go_to_first_page.disabled = True

        if page < max - 1:
            self.go_to_next_page.label = str(page + 2)
            self.go_to_next_page.disabled = False
            self.go_to_last_page.disabled = False
        else:
            self.go_to_next_page.label = "Next"
            self.go_to_next_page.disabled = True
            self.go_to_last_page.disabled = True
        self.menu.current_page = page


class Menu[P]:
    """
    A helper to have a pagination system inside of a [`LayoutView`][discord.ui.LayoutView]. It is possible to have
    multiple menus per view.

    A menu needs an instance of [`Source`][ballsdex.core.utils.menus.Source] for the pagination, and one or more
    [`Formatter`][ballsdex.core.utils.menus.Source]s which define how to display the current page. The source and
    formatters are not directly linked, but must follow the same type
    constraints, use your type checker to ensure you are using compatible classes.

    If there are multiple pages, then this class will add a row of buttons to the position you choose via
    [`init`][ballsdex.core.utils.menus.Source].

    Example
    -------
    Simple pagination for a select list, divided in sections of 25

        from ballsdex.core.utils.menus import *
        from discord.ui import *

        my_options = [...]

        view = discord.ui.LayoutView()
        select = discord.ui.Select()
        view.add_item(select)

        # max number of options for a select is 25
        source = ChunkedListSource(my_options, per_page=25)
        # the formatter is only linked to its UI element, not the source itself
        formatter = SelectFormatter(select)

        menu = Menu(self.bot, view, source, formatter)
        # by default, this will add the control buttons at the end
        await menu.init()
        await interaction.response.send_message(view=view)

    Another example with a list of `TextDisplay` items, dynamically sized to respect the view's limits

        from ballsdex.core.utils.menus import *
        from discord.ui import *

        async def generate_options():
            async for item in queryset:
                yield TextDisplay("## Item title\\nItem description...")

        view = discord.ui.LayoutView()
        container = discord.ui.Container()
        container.add_item(Section(
            TextDisplay("# Message title"),
            TextDisplay("Message subtitle"),
            accessory=Thumbnail(user.display_avatar_url),
        )
        container.add_item(Separator())

        source = ListSource(await dynamic_chunks(view, generate_options()))
        formatter = ItemFormatter(container, position=2)  # insert after separator
        menu = Menu(self.bot, view, source, formatter)
        await menu.init()
        await interaction.response.send_message(view=view)

    Tip
    ---
    Using a type checker can reveal incompatible types

        from ballsdex.core.utils.menus import *

        source = ModelSource(BallInstance.objects.filter(player=player))
        formatter = TextSource(item)
        menu = Menu(self.bot, view, source, formatter)
        # Argument of type "TextSource" cannot be assigned to parameter "formatters" of type "Formatter[P@Menu, Any]" in function "__init__"
        #   "TextSource" is not assignable to "Formatter[QuerySet[BallInstance], Any]"

    Parameters
    ----------
    bot: BallsDexBot
        The bot instance. Unused by itself, but some formatters may find it useful to have it available.
    view: LayoutView
        The view you are attaching to. This is incompatible with V1 views.
    source: Source[P]
        The source instance providing the elements to paginate
    *formatters: Formatter[P, discord.ui.Item]
        One or more formatters which will display the data from the source. They are attached to an item that belongs to
        the view.
    """  # noqa: E501

    def __init__(self, bot: "BallsDexBot", view: LayoutView, source: Source[P], *formatters: Formatter[P, Any]):
        self.bot = bot
        self.view = view
        self.formatters = formatters
        for formatter in formatters:
            formatter.configure(self)
        self.source = source
        self.current_page = 0
        self.controls = Controls(self)

    @classmethod
    def countryballs(
        cls: type[Menu[QuerySet[BallInstance]]],
        bot: "BallsDexBot",
        view: LayoutView,
        select: discord.ui.Select,
        queryset: "QuerySet[BallInstance]",
    ):
        source = ModelSource(queryset)
        formatter = CountryballFormatter(select)
        return cls(bot, view, source, formatter)

    async def init(self, position: int | None = None, container: discord.ui.Container | None = None):
        """
        Prepare the menu before sending.

        Parameters
        ----------
        position: int | None
            The position at which to insert the control buttons. If `None`, this will be at the end.
        container: discord.ui.Container | None
            If provided, the control buttons will be inserted inside the container instead of the outer view. The
            `position` parameter is respected within the container.
        """
        await self.source.prepare()
        await self.set_page(0)
        if self.source.get_max_pages() <= 1:
            return
        item = container or self.view
        if not position:
            item.add_item(self.controls)
            return

        # View only supports appending at the end, not inserting, so it's done manually
        self.view._add_count(self.controls._total_count)
        if container:
            container._update_view(self.view)
            self.controls._parent = container
        if position:
            item._children.insert(position, self.controls)
        else:
            item._children.append(self.controls)

    async def set_page(self, page: int):
        p = await self.source.get_page(page)
        for formatter in self.formatters:
            await formatter.format_page(p)
        self.controls.edit_buttons(page)

    async def show_page(self, interaction: Interaction, page: int):
        await interaction.response.defer()
        await self.set_page(page)
        await interaction.edit_original_response(view=self.view)
