from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ui import Container, Section, Separator, TextDisplay, Thumbnail
from django.db.models import Count, Q

from ballsdex.core.discord import LayoutView
from ballsdex.core.utils.menus import ChunkedListSource, ItemFormatter, Menu
from ballsdex.core.utils.transformers import BallEnabledTransform, SpecialEnabledTransform
from bd_models.models import Player
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

medals = {1: "🥇", 2: "🥈", 3: "🥉"}


@app_commands.command()
async def leaderboard(
    interaction: discord.Interaction["BallsDexBot"],
    *,
    countryball: BallEnabledTransform | None = None,
    special: SpecialEnabledTransform | None = None,
):
    """
    Show the top 10 players with the most countryballs in BallsDex.

    Parameters
    ----------
    countryball: Ball | None
        Filter the leaderboard by a specific countryball.
    special: Special | None
        Filter the leaderboard by a specific special.
    """
    await interaction.response.defer(thinking=True)

    stats: list[tuple[Player | int, int]]
    queryset = Player.objects.all()
    filters = Q()
    if countryball:
        filters &= Q(balls__ball=countryball)
    if special:
        filters &= Q(balls__special=special)
    queryset = queryset.filter(filters).annotate(count=Count("balls", distinct=True)).order_by("-count")[:10]
    ball_txt = countryball.country if countryball else ""
    special_txt = special.name if special else ""
    combined_parts = [str(x) for x in [special_txt, ball_txt] if x]
    combined = " ".join(combined_parts)
    if not await queryset.aexists():
        await interaction.response.send_message(
            f"Players don't have any {settings.plural_collectible_name} {combined}", ephemeral=True
        )
        return
    stats = [(x, x.count) async for x in queryset]  # type: ignore

    sorted_stats = sorted(stats, key=lambda x: x[1], reverse=True)
    entries = []
    total_count = 0

    for top, (player, count) in enumerate(sorted_stats, start=1):
        try:
            user_id = player if isinstance(player, int) else player.discord_id
            user = await interaction.client.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            continue

        total_count += count
        entries.append(
            Section(
                TextDisplay(f"### Top {medals.get(top, top)}\n> User: {user.display_name}\n> Count: {count}"),
                accessory=Thumbnail(media=user.display_avatar.url),
            )
        )

    view = LayoutView()
    view.restrict_author(interaction.user.id)
    container = Container(
        TextDisplay(
            f"# {settings.bot_name.capitalize()} Leaderboard{f' ({combined})' if len(str(combined)) > 0 else ''}"
        ),
        TextDisplay(f"-# Total: {total_count}"),
        Separator(),
    )
    view.add_item(container)
    menu = Menu(interaction.client, view, ChunkedListSource(entries, 3), ItemFormatter(container, 2))
    await menu.init()
    await interaction.followup.send(view=view, allowed_mentions=discord.AllowedMentions(users=False))
