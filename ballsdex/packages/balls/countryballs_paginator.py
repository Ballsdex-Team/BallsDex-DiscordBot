from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord

from ballsdex.core.utils import menus
from ballsdex.settings import settings
from bd_models.models import BallInstance

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot


class CountryballsViewer(menus.CountryballsSource):
    async def selected(self, interaction: discord.Interaction["BallsDexBot"], queryset: "QuerySet[BallInstance]"):
        content, file, view = await (await queryset.aget()).prepare_for_message(interaction)
        await interaction.followup.send(content=content, file=file, view=view)
        file.close()


class DuplicateSource(menus.SelectListPageSource):
    def __init__(self, dupe_type: str, entries: list[discord.SelectOption], **select_kwargs: Any):
        self.dupe_type = dupe_type
        super().__init__(entries, **select_kwargs)

    async def callback(self, interaction: discord.Interaction["BallsDexBot"], select, values):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if self.dupe_type == settings.plural_collectible_name:
            balls = await BallInstance.objects.filter(
                ball_id=values[0], player__discord_id=interaction.user.id
            ).acount()
        else:
            balls = await BallInstance.objects.filter(
                special_id=values[0], player__discord_id=interaction.user.id
            ).acount()

        plural = settings.collectible_name if balls == 1 else settings.plural_collectible_name
        await interaction.followup.send(f"You have {balls:,} {values[0]} {plural}.")
