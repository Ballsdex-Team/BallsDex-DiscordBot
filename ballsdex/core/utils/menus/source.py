from math import ceil
from typing import TYPE_CHECKING, Sequence

import discord

from ballsdex.core.utils.formatting import pagify

if TYPE_CHECKING:
    from django.db.models import Model, QuerySet

    from ballsdex.core.bot import BallsDexBot

type Interaction = discord.Interaction["BallsDexBot"]


class Source[P]:
    """
    A source of long items to paginate and display over Discord.
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


class ListSource[P](Source[P]):
    def __init__(self, items: list[P]):
        super().__init__()
        self.items = items

    def get_max_pages(self) -> int:
        return len(self.items)

    async def get_page(self, page_number: int):
        return self.items[page_number]


class ChunkedListSource[P](Source[list[P]]):
    def __init__(self, items: list[P], per_page: int = 25):
        super().__init__()
        self.items = items
        self.per_page = per_page

    def get_max_pages(self) -> int:
        return ceil(len(self.items) / self.per_page)

    async def get_page(self, page_number: int):
        return self.items[page_number * self.per_page : (page_number + 1) * self.per_page]


class TextSource(ListSource[str]):
    def __init__(
        self,
        text: str,
        delims: Sequence[str] = ["\n#", "\n##", "\n###", "\n\n", "\n"],
        *,
        priority: bool = True,
        escape_mass_mentions: bool = True,
        shorten_by: int = 8,
        page_length: int = 5900,
    ):
        pages = pagify(
            text,
            delims,
            priority=priority,
            escape_mass_mentions=escape_mass_mentions,
            shorten_by=shorten_by,
            page_length=page_length,
        )
        super().__init__(list(pages))


class ModelSource[M: "Model"](Source["QuerySet[M]"]):
    def __init__(self, queryset: "QuerySet[M]", per_page: int = 25) -> None:
        super().__init__()
        self.per_page = per_page
        self.queryset = queryset

    async def prepare(self):
        self.max = ceil(await self.queryset.acount() / self.per_page)
        if self.max == 0:
            raise ValueError("Queryset is empty")

    def get_max_pages(self) -> int:
        return self.max

    async def get_page(self, page_number: int) -> "QuerySet[M]":
        return self.queryset[page_number * self.per_page : (page_number + 1) * self.per_page]
