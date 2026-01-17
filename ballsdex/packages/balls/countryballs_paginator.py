from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ui import ActionRow, Select, TextDisplay
from django.db.models import Count, Exists, OuterRef, Q, Value

from ballsdex.core.discord import LayoutView
from bd_models.models import Ball, BallInstance, Player, Special
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class CountryballsViewer(LayoutView):
    header = TextDisplay("")
    select_row = ActionRow()

    @select_row.select()
    async def selected(self, interaction: discord.Interaction["BallsDexBot"], select: Select):
        await interaction.response.defer(thinking=True)
        ball = await BallInstance.objects.prefetch_related("trade_player").aget(pk=select.values[0])
        content, file, view = await ball.prepare_for_message(interaction)
        await interaction.followup.send(content=content, file=file, view=view)
        file.close()


class CountryballsDuplicateSource(LayoutView):
    def __init__(self, is_special: bool, *, timeout: float | None = 180) -> None:
        super().__init__(timeout=timeout)
        self.is_special = is_special

    header = TextDisplay("")
    select_row = ActionRow()

    @select_row.select()
    async def callback(self, interaction: discord.Interaction["BallsDexBot"], select: Select):
        await interaction.response.defer(thinking=True, ephemeral=True)

        player = await Player.objects.aget(discord_id=interaction.user.id)
        balls_query = (
            BallInstance.objects.filter(player=player)
            .values("player_id")
            .annotate(total=Count("id"), traded=Count("id", filter=Q(trade_player_id__isnull=False)))
        )
        countryball = None
        if self.is_special:
            special = await Special.objects.aget(id=select.values[0])
            name = special.name
            balls_query = balls_query.filter(special=special).annotate(specials=Value("1"))
            grouped_query = (
                BallInstance.objects.filter(player=player, special=special)
                .prefetch_related("ball")
                .values("ball__country")
                .annotate(count=Count("ball__country"))
                .order_by("-count", "ball__country")
            )
        else:
            countryball = await Ball.objects.aget(id=select.values[0])
            name = countryball.country
            balls_query = balls_query.filter(ball=countryball).annotate(
                specials=Count(
                    "id",
                    filter=Q(special_id__isnull=False)
                    & ~Exists(Special.objects.filter(hidden=True, id=OuterRef("special_id"))),
                )
            )
            grouped_query = (
                BallInstance.objects.filter(player=player, ball=countryball)
                .exclude(special_id=None)
                .exclude(special__hidden=True)
                .values("special__name")
                .annotate(count=Count("special__name"))
                .order_by("-count", "special__name")
            )

        counts = await balls_query.values("total", "traded", "specials").aget()

        if not counts:
            await interaction.followup.send(f"You don't have any {settings.plural_collectible_name} yet.")
            return
        special_emojis = {x.name: x.emoji async for x in Special.objects.filter(hidden=False)}

        desc = (
            f"**Total**: {counts['total']:,} ({counts['total'] - counts['traded']:,} caught, "
            f"{counts['traded']:,} received from trade)\n"
        )
        if self.is_special:
            desc = f"**{settings.plural_collectible_name.title()}**: (Top 15)\n"
            async for country in grouped_query.values("ball__country", "ball__emoji_id", "count")[:15]:
                emoji = interaction.client.get_emoji(country["ball__emoji_id"])
                desc += f"{emoji} {country['ball__country']}: {country['count']:,}\n"
        else:
            desc += f"**Total Specials**: {counts['specials']:,}\n"
            if counts["specials"]:
                desc += "**Specials**:\n"
            async for special in grouped_query.values("special__name", "count"):
                emoji = special_emojis.get(special["special__name"], "")
                desc += f"{emoji} {special['special__name']}: {special['count']:,}\n"

        embed = discord.Embed(title=f"{name} Collection", description=desc, color=discord.Color.blurple())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        if countryball:
            emoji = interaction.client.get_emoji(countryball.emoji_id)
            if emoji:
                embed.set_thumbnail(url=emoji.url)
        await interaction.followup.send(embed=embed)
