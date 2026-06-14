from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ui import Container, Section, Separator, TextDisplay, Thumbnail
from django.db.models import Count

from ballsdex.core.discord import LayoutView
from ballsdex.core.utils.menus import ChunkedListSource, ItemFormatter, Menu
from ballsdex.core.utils.transformers import BallEnabledTransform, SpecialEnabledTransform
from bd_models.models import BallInstance, Player
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

    filters = {}
    if special:
        filters["special"] = special
    if countryball:
        filters["ball"] = countryball

    query = (
        BallInstance.objects.filter(**filters)
        .values("player_id")
        .annotate(ball_count=Count("id"))
        .order_by("-ball_count")[:10]
    )
    ball_txt = countryball.country if countryball else ""
    special_txt = special.name if special else ""
    combined_parts = [str(x) for x in [special_txt, ball_txt] if x]
    combined = " ".join(combined_parts)
    if not await query.aexists():
        await interaction.followup.send(
            f"Players don't have any {settings.plural_collectible_name} {combined}", ephemeral=True
        )
        return
    player_ids = [(x["player_id"], x["ball_count"]) async for x in query]
    players_qs = [x async for x in Player.objects.filter(id__in=[x[0] for x in player_ids])]
    players = {p.pk: p for p in players_qs}
    instances = [{"player": players[x[0]], "ball_count": x[1]} for x in player_ids]

    entries = []
    total_count = 0

    for top, instance in enumerate(instances, start=1):
        player = instance["player"]
        try:
            user_id = player if isinstance(player, int) else player.discord_id
            user = await interaction.client.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            continue

        total_count += instance["ball_count"]
        entries.append(
            Section(
                TextDisplay(
                    f"### Top {medals.get(top, top)}\n> User: {user.display_name}\n> Count: {instance['ball_count']}"
                ),
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
