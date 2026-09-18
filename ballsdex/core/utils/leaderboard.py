"""
The top players for a value, shown by pages with their avatar: treasures owned, currency...
"""

from typing import TYPE_CHECKING, Callable

import discord
from discord.ui import Container, Section, Separator, TextDisplay, Thumbnail

from ballsdex.core.discord import LayoutView
from ballsdex.core.utils.menus import ChunkedListSource, ItemFormatter, Menu
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
LEADERBOARD_SIZE = 20
PER_PAGE = 5
# a few more rows are queried than shown, some users may not be reachable anymore
EXTRA_ROWS = 10


async def resolve_user(client: "BallsDexBot", discord_id: int) -> discord.User | None:
    if user := client.get_user(discord_id):
        return user
    try:
        return await client.fetch_user(discord_id)
    except (discord.NotFound, discord.HTTPException):
        return None


async def send_leaderboard(
    interaction: discord.Interaction["BallsDexBot"],
    *,
    title: str,
    subtitle: str,
    ranking: list[tuple[int, int]],
    describe: Callable[[int], str],
):
    """
    Send the leaderboard as a follow-up of the deferred interaction.

    Parameters
    ----------
    title: str
        The title of the leaderboard.
    subtitle: str
        A line shown below the title, like the total counted.
    ranking: list[tuple[int, int]]
        Discord IDs and values of the best players, best first. Query `LEADERBOARD_SIZE + EXTRA_ROWS` rows.
    describe: Callable[[int], str]
        Formats the value of a player, like "Count: 12".
    """
    entries: list[Section] = []
    for discord_id, value in ranking:
        if len(entries) == LEADERBOARD_SIZE:
            break
        user = await resolve_user(interaction.client, discord_id)
        if user is None:
            continue
        top = len(entries) + 1
        entries.append(
            Section(
                TextDisplay(f"### Top {MEDALS.get(top, top)}\n> User: {user.display_name}\n> {describe(value)}"),
                accessory=Thumbnail(media=user.display_avatar.url),
            )
        )

    view = LayoutView()
    view.restrict_author(interaction.user.id)
    container = Container(
        TextDisplay(f"# {title}"), TextDisplay(f"-# {subtitle}"), Separator(), accent_colour=settings.embed_colour
    )
    view.add_item(container)
    menu = Menu(interaction.client, view, ChunkedListSource(entries, PER_PAGE), ItemFormatter(container, 2))
    await menu.init()
    await interaction.followup.send(view=view, allowed_mentions=discord.AllowedMentions(users=False))
