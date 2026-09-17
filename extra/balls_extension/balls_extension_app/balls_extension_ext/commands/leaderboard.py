from typing import TYPE_CHECKING

import discord
from currency_app.models import Item, ItemBall
from discord import app_commands
from discord.ui import Container, Section, Separator, TextDisplay, Thumbnail
from django.db.models import Count

from ballsdex.core.discord import LayoutView
from ballsdex.core.utils.menus import ChunkedListSource, ItemFormatter, Menu
from ballsdex.core.utils.transformers import BallEnabledTransform, SpecialEnabledTransform, TTLModelTransformer
from bd_models.models import BallInstance, Player
from settings.models import settings

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot

medals = {1: "🥇", 2: "🥈", 3: "🥉"}

LEADERBOARD_SIZE = 20
PER_PAGE = 5


class PackTransformer(TTLModelTransformer[Item]):
    name = "pack"
    model = Item

    def get_queryset(self) -> "QuerySet[Item]":
        # only packs with a list of treasures to pick from have pack-only treasures
        return super().get_queryset().filter(balls__isnull=False).distinct()


PackTransform = app_commands.Transform[Item, PackTransformer]


async def resolve_user(client: "BallsDexBot", discord_id: int) -> discord.User | None:
    if user := client.get_user(discord_id):
        return user
    try:
        return await client.fetch_user(discord_id)
    except (discord.NotFound, discord.HTTPException):
        return None


@app_commands.command()
async def leaderboard(
    interaction: discord.Interaction["BallsDexBot"],
    *,
    countryball: BallEnabledTransform | None = None,
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
        query = query.filter(special=special)
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

    # a few more rows than needed, some users may not be reachable anymore
    ranking = [
        (row["player_id"], row["ball_count"])
        async for row in query.values("player_id")
        .annotate(ball_count=Count("id"))
        .order_by("-ball_count")[: LEADERBOARD_SIZE + 10]
    ]
    players = {p.pk: p async for p in Player.objects.filter(id__in=[player_id for player_id, _ in ranking])}

    entries: list[Section] = []
    for player_id, ball_count in ranking:
        if len(entries) == LEADERBOARD_SIZE:
            break
        user = await resolve_user(interaction.client, players[player_id].discord_id)
        if user is None:
            continue
        top = len(entries) + 1
        share = ball_count / totals["items"] * 100
        entries.append(
            Section(
                TextDisplay(
                    f"### Top {medals.get(top, top)}\n"
                    f"> User: {user.display_name}\n"
                    f"> Count: {ball_count:,} ({share:.1f}% of all)"
                ),
                accessory=Thumbnail(media=user.display_avatar.url),
            )
        )

    view = LayoutView()
    view.restrict_author(interaction.user.id)
    container = Container(
        TextDisplay(f"# {settings.bot_name.capitalize()} Leaderboard{f' ({combined})' if combined else ''}"),
        TextDisplay(
            f"-# Total: {totals['items']:,} {settings.plural_collectible_name} owned by {totals['players']:,} players"
        ),
        Separator(),
        accent_colour=settings.embed_colour,
    )
    view.add_item(container)
    menu = Menu(interaction.client, view, ChunkedListSource(entries, PER_PAGE), ItemFormatter(container, 2))
    await menu.init()
    await interaction.followup.send(view=view, allowed_mentions=discord.AllowedMentions(users=False))
