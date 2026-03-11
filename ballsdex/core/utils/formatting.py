from typing import Iterator, Sequence

import discord


def pagify(
    text: str,
    delims: Sequence[str] = ["\n"],
    *,
    priority: bool = False,
    escape_mass_mentions: bool = True,
    shorten_by: int = 8,
    page_length: int = 2000,
    prefix: str = "",
    suffix: str = "",
) -> Iterator[str]:
    """
    Generate multiple pages from the given text.

    Parameters
    ----------
    text: str
        The content to pagify and send.
    delims: Sequence[str]
        Characters where page breaks will occur. If no delimiters are found
        in a page, the page will break after `page_length` characters.
        By default this only contains the newline.

    Other Parameters
    ----------------
    priority: bool
        Set to `True` to choose the page break delimiter based on the
        order of `delims`. Otherwise, the page will always break at the
        last possible delimiter.
    escape_mass_mentions: bool
        If `True`, any mass mentions (here or everyone) will be
        silenced.
    shorten_by: int
        How much to shorten each page by. Defaults to 8.
    page_length: int
        The maximum length of each page. Defaults to 2000.

    Yields
    ------
    str
        Pages of the given text.
    """
    in_text = text
    page_length -= shorten_by + len(prefix) + len(suffix)
    while len(in_text) > page_length:
        this_page_len = page_length
        if escape_mass_mentions:
            this_page_len -= in_text.count("@here", 0, page_length) + in_text.count("@everyone", 0, page_length)
        closest_delim = (in_text.rfind(d, 1, this_page_len) for d in delims)
        if priority:
            closest_delim = next((x for x in closest_delim if x > 0), -1)
        else:
            closest_delim = max(closest_delim)
        closest_delim = closest_delim if closest_delim != -1 else this_page_len
        if escape_mass_mentions:
            to_send = escape(in_text[:closest_delim], mass_mentions=True)
        else:
            to_send = in_text[:closest_delim]
        if len(to_send.strip()) > 0:
            yield f"{prefix}{to_send}{suffix}"
        in_text = in_text[closest_delim:]

    if len(in_text.strip()) > 0:
        in_text = f"{prefix}{in_text}{suffix}"
        if escape_mass_mentions:
            yield escape(in_text, mass_mentions=True)
        else:
            yield in_text


def escape(text: str, *, mass_mentions: bool = False, formatting: bool = False) -> str:
    """
    Get text with all mass mentions or markdown escaped.

    Parameters
    ----------
    text: str
        The text to be escaped.
    mass_mentions: bool
        Set to `True` to escape mass mentions in the text.
    formatting: bool
        Set to `True` to escape any markdown formatting in the text.

    Returns
    -------
    str
        The escaped text.
    """
    if mass_mentions:
        text = text.replace("@everyone", "@\u200beveryone")
        text = text.replace("@here", "@\u200bhere")
    if formatting:
        text = discord.utils.escape_markdown(text)
    return text
