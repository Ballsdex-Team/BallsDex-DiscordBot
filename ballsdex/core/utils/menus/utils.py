from collections.abc import AsyncIterable, Iterable

import discord


async def dynamic_chunks[I: discord.ui.Item](view: discord.ui.LayoutView, source: AsyncIterable[I]) -> list[list[I]]:
    """
    Transform an iterable of `discord.ui.Item`s into a list of lists. Each sublist is guaranteed to fit the limits of
    the view given as argument.

    This is useful combined with `ItemFormatter` to display a dynamically-sized list of items.

    Warning
    -------
        This will ensure the limits of the view are respected at the time this function is called. Do not append new
        items to your view after calling this function as the results will be inaccurate.

    Parameters
    ----------
    view: discord.ui.LayoutView
        The finished view that will have the items appended to. The position does not matter as it only checks for
        global limits.
    source: AsyncIterable[I]
        The generator providing the items. This is asynchronous in case you are doing this along an asynchronous
        iterator, like a database query or a Discord paginator.

    Returns
    -------
    list[list[I]]
        The chunked list of items.
    """
    sections = []
    current_chunk = []
    async for item in source:
        view.add_item(item)
        current_chunk.append(item)
        if view.content_length() > 5900 or view.total_children_count > 30:
            sections.append(current_chunk)
            for old_item in current_chunk:
                view.remove_item(old_item)
            current_chunk = []
    if current_chunk:
        sections.append(current_chunk)
        for old_item in current_chunk:
            view.remove_item(old_item)
    return sections


async def iter_to_async[T](source: Iterable[T]) -> AsyncIterable[T]:
    """
    A helper to transform a synchronous iterable into an asynchronous one, useful for `dynamic_chunks`.
    """
    for x in source:
        yield x
