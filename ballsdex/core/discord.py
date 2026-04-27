# pyright: reportIncompatibleMethodOverride=false

import logging
from typing import TYPE_CHECKING, Any, Self

import discord
from discord.ui import Item
from discord.ui.view import BaseView as DiscordBaseView

from ballsdex.core import tracing

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

type Interaction = discord.Interaction[BallsDexBot]

log = logging.getLogger("ballsdex.core.discord")

# https://discord.com/developers/docs/topics/opcodes-and-status-codes#json-json-error-codes
UNKNOWN_INTERACTION = {10062, 10015}


async def _error_handler(interaction: Interaction, error: Exception) -> bool:
    if isinstance(error, discord.NotFound) and error.code in UNKNOWN_INTERACTION:
        log.warning("Expired interaction", exc_info=error)
        return True
    if not interaction.is_expired() and interaction.type != discord.InteractionType.autocomplete:
        send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await send("An error occured. Contact support if this persists.", ephemeral=True)
    return False


def _trade_span_tags(holder: object) -> dict[str, Any]:
    """Pull `trade.id` from any object that opts in by setting it (TradeInstance, SetMoneyModal)."""
    return {"trade.id": getattr(holder, "trade_id", None)}


def _trade_span_links(holder: object) -> list | None:
    origin = getattr(holder, "trade_origin_context", None)
    return [origin] if origin is not None else None


class BaseView(DiscordBaseView):
    def restrict_author(self, discord_id: int):
        self.discord_id = discord_id

    async def on_error(self, interaction: Interaction, error: Exception, item: Item[Self]):
        if not await _error_handler(interaction, error):
            return await super().on_error(interaction, error, item)

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        if not await interaction.client.blacklist_check(interaction):
            return False
        if author := getattr(self, "discord_id", None):
            if author != interaction.user.id:
                await interaction.response.send_message("You are not allowed to interact with this.", ephemeral=True)
                return False
        return await super().interaction_check(interaction)

    async def _scheduled_task(self, item: Item[Self], interaction: Interaction):
        with tracing.span(
            "discord.component",
            resource=f"{type(self).__name__}.{getattr(item, 'custom_id', type(item).__name__)}",
            tags={
                "discord.view.class": type(self).__name__,
                "discord.item.type": type(item).__name__,
                "discord.item.custom_id": getattr(item, "custom_id", None),
                "discord.user.id": interaction.user.id,
                "discord.guild.id": interaction.guild_id,
                **_trade_span_tags(self),
            },
            links=_trade_span_links(self),
        ):
            await super()._scheduled_task(item, interaction)


class View(discord.ui.View, BaseView):
    pass


class LayoutView(discord.ui.LayoutView, BaseView):
    pass


class Container(discord.ui.Container[LayoutView]):
    async def interaction_check(self, interaction: Interaction, /) -> bool:
        if not await interaction.client.blacklist_check(interaction):
            return False
        return await super().interaction_check(interaction)


class Modal(discord.ui.Modal):
    async def on_error(self, interaction: Interaction, error: Exception):
        if not await _error_handler(interaction, error):
            return await super().on_error(interaction, error)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if not await interaction.client.blacklist_check(interaction):
            return False
        return await super().interaction_check(interaction)

    async def _scheduled_task(self, interaction: Interaction, components, resolved):
        with tracing.span(
            "discord.modal_submit",
            resource=f"{type(self).__name__}.on_submit",
            tags={
                "discord.modal.class": type(self).__name__,
                "discord.modal.custom_id": getattr(self, "custom_id", None),
                "discord.user.id": interaction.user.id,
                "discord.guild.id": interaction.guild_id,
                **_trade_span_tags(self),
            },
            links=_trade_span_links(self),
        ):
            await super()._scheduled_task(interaction, components, resolved)

    # This only exists to suppress type warnings about ClientT
    async def on_submit(self, interaction: Interaction):
        return await super().on_submit(interaction)
