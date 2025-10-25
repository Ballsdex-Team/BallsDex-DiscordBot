from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ui import ActionRow, Select, TextDisplay

from ballsdex.core.discord import LayoutView
from bd_models.models import BallInstance

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
    header = TextDisplay("")
    select_row = ActionRow()

    @select_row.select()
    async def callback(self, interaction: discord.Interaction["BallsDexBot"], select: Select):
        await interaction.response.defer()
