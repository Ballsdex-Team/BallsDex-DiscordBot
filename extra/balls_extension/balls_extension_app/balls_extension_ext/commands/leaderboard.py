from typing import TYPE_CHECKING

import discord
from currency_app.models import Item, ItemBall
from discord import app_commands
from django.db.models import Count

from ballsdex.core.utils.leaderboard import EXTRA_ROWS, LEADERBOARD_SIZE, send_leaderboard
from ballsdex.core.utils.transformers import BallObtainableTransform, SpecialEnabledTransform, TTLModelTransformer
from bd_models.models import BallInstance, Player, special_filter
from settings.models import settings

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot


class PackTransformer(TTLModelTransformer[Item]):
    name = "pack"
    model = Item

    def get_queryset(self) -> "QuerySet[Item]":
        # only packs with a list of treasures to pick from have pack-only treasures
        return super().get_queryset().filter(balls__isnull=False).distinct()


PackTransform = app_commands.Transform[Item, PackTransformer]


@app_commands.command()
async def leaderboard(
    interaction: discord.Interaction["BallsDexBot"],
    *,
    countryball: BallObtainableTransform | None = None,
    special: SpecialEnabledTransform | None = None,
    pack_only: bool = False,
    pack: PackTransform | None = None,
):
    """
    Show the top 20 players with the most countryballs in BallsDex.

    Parameters
    ----------
    countryball: Ball | None
        Filter the leaderboard by a specific countryball.
    special: Special | None
        Filter the leaderboard by a specific special.
    pack_only: bool
        Only count the treasures that can only be obtained from packs.
    pack: Item | None
        Only count the treasures that can be obtained from this pack.
    """
    await interaction.response.defer(thinking=True)

    query = BallInstance.objects.all()
    if special:
        query = query.filter(special_filter(special))
    if countryball:
        query = query.filter(ball=countryball)
    if pack:
        query = query.filter(ball_id__in=ItemBall.objects.filter(item=pack).values("ball_id"))
    elif pack_only:
        query = query.filter(ball_id__in=ItemBall.objects.values("ball_id"))

    filter_names = [x for x in (special and special.name, countryball and countryball.country) if x]
    if pack:
        filter_names.append(f"{pack.name} pack")
    elif pack_only:
        filter_names.append("pack-only")
    combined = " ".join(filter_names)

    totals = await query.aaggregate(items=Count("id"), players=Count("player_id", distinct=True))
    if not totals["items"]:
        await interaction.followup.send(
            f"Players don't have any {combined + ' ' if combined else ''}{settings.plural_collectible_name} yet.",
            ephemeral=True,
        )
        return

    counts = [
        (row["player_id"], row["ball_count"])
        async for row in query.values("player_id")
        .annotate(ball_count=Count("id"))
        .order_by("-ball_count")[: LEADERBOARD_SIZE + EXTRA_ROWS]
    ]
    discord_ids = {
        player_id: discord_id
        async for player_id, discord_id in Player.objects.filter(id__in=[x for x, _ in counts]).values_list(
            "id", "discord_id"
        )
    }
    await send_leaderboard(
        interaction,
        title=f"{settings.bot_name.capitalize()} Leaderboard{f' ({combined})' if combined else ''}",
        subtitle=f"Total: {totals['items']:,} {settings.plural_collectible_name} "
        f"owned by {totals['players']:,} players",
        ranking=[(discord_ids[player_id], count) for player_id, count in counts],
        describe=lambda count: f"Count: {count:,} ({count / totals['items'] * 100:.1f}% of all)",
    )
