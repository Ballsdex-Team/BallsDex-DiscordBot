from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ballsdex.core.utils.transformers import TTLModelTransformer
from ballsdex.core.utils.utils import is_staff

from .models import EventPass

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot


class EventPassTransformer(TTLModelTransformer[EventPass]):
    name = "pass"
    model = EventPass

    def get_queryset(self) -> "QuerySet[EventPass]":
        # drafts are listed too, so staff can open the pass they are building. They are filtered out of the
        # suggestions of everyone else below, and the commands refuse them anyway.
        return super().get_queryset()

    async def get_options(
        self, interaction: discord.Interaction["BallsDexBot"], value: str
    ) -> list[app_commands.Choice[str]]:
        options = await super().get_options(interaction, value)
        if await is_staff(interaction):
            return options
        drafts = {str(pk) for pk, event_pass in self.items.items() if event_pass.status == EventPass.Status.DRAFT}
        return [choice for choice in options if choice.value not in drafts]


EventPassTransform = app_commands.Transform[EventPass, EventPassTransformer]
