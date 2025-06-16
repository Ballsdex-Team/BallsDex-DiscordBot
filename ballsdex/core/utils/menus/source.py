"""
The pagination sources to be used with a menu.

This is heavily inspired from discord.ext.menus, written by Danny Y. (Rapptz)
The license of this repo can be found in this folder.
https://github.com/Rapptz/discord-ext-menus/

The code was reworked to support proper type hinting, handle recent Discord features
and utils specific to Ballsdex and its tooling.
"""

import functools
import inspect
from typing import TYPE_CHECKING, Any, AsyncIterator

import discord
from discord.ext.commands import Paginator as CommandPaginator
from discord.ui import Select

from ballsdex.settings import settings
from bd_models.models import BallInstance

if TYPE_CHECKING:
    from django.db.models import Model, QuerySet

    from ballsdex.core.bot import BallsDexBot

    from .menus import Menu

__all__ = (
    "PageSource",
    "ListPageSource",
    "FieldPageSource",
    "TextPageSource",
    "SelectPageSource",
    "SelectListPageSource",
    "AsyncIteratorPageSource",
    "ModelPageSource",
    "CountryballsSource",
)

type field = tuple[str, str]


class PageSource[P]:
    """
    The source of a pagination. Used as the first argument to a menu paginator.

    This must provide pages of type `P` with `get_page`, and handle the method `format_page`
    to define how a page looks.
    """

    async def prepare(self):
        """
        Called before starting the pagination.
        """
        pass

    def is_paginating(self) -> bool:
        """
        Defines if the source is currently paginating. If `False`, this means there is no
        need to paginate, and no control buttons will be shown.
        """
        raise NotImplementedError

    def get_max_pages(self) -> int:
        """
        Returns the maximum number of pages in the iterable.
        """
        raise NotImplementedError

    async def get_page(self, page_number: int) -> P:
        """
        Returns one page of type `P`.

        Parameters
        ----------
        page_number: int
            The page number requested. Cannot be negative, and strictly lower than the result of
            `get_max_pages`.
        """
        raise NotImplementedError

    async def format_page(
        self, menu: "Menu[P]", page: P
    ) -> str | discord.Embed | tuple[discord.ui.Item[Menu[P]]] | dict[str, Any]:
        """
        Formats the page given as argument to something suitable to be displayed.

        Parameters
        ----------
        menu: Menu[P]
            The menu instance linked to the page source.
        page: P
            The page that has to be displayed

        Returns
        -------
        str | discord.Embed | tuple[discord.ui.Item[Menu[P]]] | dict[str, Any]
            The result of this function edits the message of the pagination. Multiple types are
            supported:

            *   `str`: Edits the content of the message
            *   `discord.Embed`: Edits the content of the message embed
            *   `tuple[discord.ui.Item[Menu[P]]]`: Adds components to the current message. Keep in
                mind two rows are already used for menu controls.
        """
        raise NotImplementedError


class ListPageSource[V](PageSource[list[V]]):
    """
    A `PageSource` based on a list with items of type `V`.

    Parameters
    ----------
    entries: list[V]
        The list of entries for the menu.
    per_page: int
        Number of entries that should be returned per page.
    """

    def __init__(self, entries: list[V], *, per_page: int):
        self.entries = entries
        self.per_page = per_page

        pages, left_over = divmod(len(entries), per_page)
        if left_over:
            pages += 1

        self._max_pages = pages

    def is_paginating(self):
        return len(self.entries) > self.per_page

    def get_max_pages(self):
        return self._max_pages

    async def get_page(self, page_number: int) -> list[V]:
        """
        Returns a slice of the sequence for the given page number.

        Returns
        -------
        list[T]
            The data for the given page, of max size `per_page`.
        """
        base = page_number * self.per_page
        return self.entries[base : base + self.per_page]


class FieldPageSource(ListPageSource[field]):
    """
    A `PageSource` that requires ``(field_name, field_value)`` tuple items, to be used as
    embed fields.

    Attributes
    ----------
    embed: discord.Embed
        The embed to be used as a base. You can edit it to add more attributes, but all fields
        will always be cleared.

    Parameters
    ----------
    entries: list[tuple[str, str]]
        The list of embed fields to display
    per_page: int
        Override the number of fields to display per page. Defaults to 12.
    inline: bool
        Whether to display all fields inline. Defaults to `False`.
    """

    def __init__(self, entries: list[field], *, per_page: int = 12, inline: bool = False) -> None:
        super().__init__(entries, per_page=per_page)
        self.embed: discord.Embed = discord.Embed(colour=discord.Colour.blurple())
        self.inline: bool = inline

    async def format_page(self, menu, page) -> discord.Embed:
        self.embed.clear_fields()

        for key, value in page:
            self.embed.add_field(name=key, value=value, inline=self.inline)

        maximum = self.get_max_pages()
        if maximum > 1:
            text = f"Page {menu.current_page + 1}/{maximum}"
            self.embed.set_footer(text=text)

        return self.embed


class TextPageSource(ListPageSource[str]):
    """
    A simple source to display a long text over multiple pages.

    Parameters
    ----------
    text: str
        The long text to display. If the length is shorter than `max_size`, then there will be no
        pagination.
    prefix: str
        Prefix to prepend to each slice of the text. Defaults to "```"
    suffix: str
        Suffix to append to each slice of the text. Defaults to "```"
    page_count: bool
        Include the page count at the bottom or not. Defaults to `True`.
    max_size: int
        Maximum size of one page. Defaults to 2000 (maximum Discord message length).
    """

    def __init__(
        self, text: str, *, prefix: str = "```", suffix: str = "```", page_count: bool = True, max_size: int = 2000
    ):
        max_size = max_size - len(prefix) - len(suffix) - 2
        if page_count:
            maxlen = len(text) // max_size + 1
            max_size -= len(self._get_page_count(maxlen, maxlen)) - 1
        pages = CommandPaginator(prefix=prefix, suffix=suffix, max_size=max_size)
        for line in text.split("\n"):
            pages.add_line(line)
        self.page_count = page_count

        super().__init__(entries=pages.pages, per_page=1)

    def _get_page_count(self, current_page: int, maximum: int) -> str:
        return f"-#Page {current_page + 1}/{maximum}" if maximum > 1 else ""

    async def format_page(self, menu, page) -> str:
        if self.page_count:
            return f"{page}\n{self._get_page_count(menu.current_page, self.get_max_pages())}"
        return page[0]


class SelectPageSource[T](PageSource[T]):
    """
    A source that provides a select menu.

    This has to be combined with another page source to provide the data, which is then
    transformed to a list of options with `get_options`.

    Attributes
    ----------
    select_kwargs: dict[str, Any]
        A list of arguments to the constructor of `discord.ui.Select`.
    select: Select[Menu[list[T]]]
        The select menu instance being used. Avoid editing directly.
    """

    select_kwargs: dict[str, Any]
    select: Select["Menu[T]"]

    async def prepare(self):
        await super().prepare()
        self.select = Select(**self.select_kwargs)
        self.select.callback = functools.partial(self.callback, select=self.select, values=self.select.values)

    async def format_page(self, menu, page):
        self.select.options = await self.get_options(menu, page)
        return (self.select,)

    async def get_options(self, menu: "Menu[T]", page: T) -> list[discord.SelectOption]:
        """
        Build the list of options for the select menu.

        Parameters
        ----------
        menu: Menu[list[T]]
            The menu instance linked to the page source.
        page: T
            The page as provided by the other page source linked.

        Returns
        -------
        list[discord.SelectOption]
            The list of options to set on the select menu. Maximum of 25.
        """
        raise NotImplementedError

    async def callback(
        self, interaction: discord.Interaction["BallsDexBot"], select: Select["Menu[T]"], values: list[str]
    ) -> None:
        """
        Callback when one or more items are selected.

        Parameters
        ----------
        interaction: discord.Interaction["BallsDexBot"]
            Interaction created by the item selection.
        select: Select[Menu[T]]
            The select menu instance.
        values: list[str]
            The list of items selected. Equivalent to ``select.values``.
        """
        pass


class SelectListPageSource(SelectPageSource[list[discord.SelectOption]], ListPageSource[discord.SelectOption]):
    """
    A shortcut class that combines `SelectPageSource` and `ListPageSource`. Simply provide
    the list of `discord.SelectOption` objects to the constructor and they will be split.
    """

    def __init__(self, entries: list[discord.SelectOption], *, per_page: int = 25):
        super().__init__(entries, per_page=per_page)

    async def get_options(
        self, menu: Menu[list[discord.SelectOption]], page: list[discord.SelectOption]
    ) -> list[discord.SelectOption]:
        return page


def _aiter[T](obj: AsyncIterator[T], *, _isasync=inspect.iscoroutinefunction):
    cls = obj.__class__
    try:
        async_iter = cls.__aiter__
    except AttributeError:
        raise TypeError("{0.__name__!r} object is not an async iterable".format(cls))

    async_iter = async_iter(obj)
    if _isasync(async_iter):
        raise TypeError("{0.__name__!r} object is not an async iterable".format(cls))
    return async_iter


class AsyncIteratorPageSource[T](PageSource[list[T]]):
    """
    A page source based on an asynchronous iterator. Useful for lazy enumerations that can't
    afford to load everything at once. This is similar to `ListPageSource`.

    Parameters
    ----------
    iterator: AsyncIterator[T]
        The asynchronous iterator that returns items of type `T`
    per_page: int
        Number of items that should be included per page.
    """

    def __init__(self, iterator: AsyncIterator[T], *, per_page: int):
        self.iterator = _aiter(iterator)
        self.per_page = per_page
        self._exhausted = False
        self._cache: list[T] = []

    async def _iterate(self, n: int):
        it = self.iterator
        cache = self._cache
        for i in range(0, n):
            try:
                elem = await it.__anext__()
            except StopAsyncIteration:
                self._exhausted = True
                break
            else:
                cache.append(elem)

    async def prepare(self):
        await super().prepare()
        # Iterate until we have at least a bit more single page
        await self._iterate(self.per_page + 1)

    def is_paginating(self) -> bool:
        return len(self._cache) > self.per_page

    async def get_page(self, page_number: int):
        if page_number < 0:
            raise IndexError("Negative page number.")

        base = page_number * self.per_page
        max_base = base + self.per_page
        if not self._exhausted and len(self._cache) <= max_base:
            await self._iterate((max_base + 1) - len(self._cache))

        entries = self._cache[base:max_base]
        if not entries and max_base > len(self._cache):
            raise IndexError("Went too far")
        return entries


class ModelPageSource[T: "Model"](AsyncIteratorPageSource[T]):
    """
    A page source for enumerating a Django database model `T`.

    This is based on `AsyncIteratorPageSource` for lazy iteration of items.

    .. warning:: This must be instanciated using the `new` class method, not with the
        synchronous constructor.
    """

    @classmethod
    async def new(cls, queryset: "QuerySet[T]", *, per_page: int = 25):
        """
        Initialize the page source. This must be awaited.

        Parameters
        ----------
        queryset: django.db.QuerySet[T]
            The base queryset to use for the iteration.
        per_page: int
            Number of objects to return per page.
        """
        cls.queryset = queryset
        cls.count = await queryset.acount()

        async def iterator():
            yielded = 0
            while yielded < cls.count:
                # first iteration gets two pages, so we also fetch two pages to have one query
                async for item in queryset[yielded:].aiterator(per_page * 2):
                    yield item
                    yielded += 1

        return cls(iterator(), per_page=per_page)

    def get_max_pages(self):
        return self.count // self.per_page + 1

    def is_paginating(self):
        return self.count > self.per_page


class ModelSelectSource[T: "Model"](ModelPageSource[T], SelectPageSource[list[T]]):
    """
    A shortcut class combining `ModelPageSource` and `SelectPageSource` for listing models in
    a select menu.

    The `format_option` function must be implemented.
    """

    async def get_options(self, menu, page) -> list[discord.SelectOption]:
        return [self.format_option(menu, x) for x in page]

    async def callback(self, interaction, select, values):
        await self.selected(interaction, self.queryset.filter(pk__in=self.select.values))

    def format_option(self, menu: Menu[list[T]], object: T) -> discord.SelectOption:
        """
        Transform a single model `T` into a `discord.SelectOption` entry.

        Parameters
        ----------
        menu: Menu[list[T]]
            The current menu instance linked to the source.
        object: T
            The Django object to format.
        """
        raise NotImplementedError

    async def selected(self, interaction: discord.Interaction["BallsDexBot"], queryset: "QuerySet[T]"):
        """
        Callback when a model is selected.

        Parameters
        ----------
        interaction: discord.Interaction["BallsDexBot"]
            Interaction created by the item selection.
        queryset: "QuerySet[T]"
            The queryset that will return the matching objects. If only one item can be selected
            (default behavior), simply do ``await queryset.aget()`` to retrieve it.
        """
        pass


class CountryballsSource(ModelSelectSource[BallInstance]):
    """
    Page source exclusively for `BallInstance`.
    """

    def format_option(self, menu, object) -> discord.SelectOption:
        emoji = menu.bot.get_emoji(int(object.countryball.emoji_id))
        favorite = f"{settings.favorited_collectible_emoji} " if object.favorite else ""
        special = object.specialcard.emoji if object.specialcard else ""
        return discord.SelectOption(
            label=f"{favorite}{special}#{object.pk:0X} {object.countryball.country}",
            description=(
                f"ATK: {object.attack}({object.attack_bonus:+d}%) "
                f"• HP: {object.health}({object.health_bonus:+d}%) • "
                f"{object.catch_date.strftime('%Y/%m/%d | %H:%M')}"
            ),
            emoji=emoji,
            value=f"{object.pk}",
        )
