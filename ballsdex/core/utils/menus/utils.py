from collections.abc import AsyncIterable, Iterable

import discord


async def dynamic_chunks[I: discord.ui.Item](view: discord.ui.LayoutView, source: AsyncIterable[I]) -> list[list[I]]:
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
    for x in source:
        yield x
