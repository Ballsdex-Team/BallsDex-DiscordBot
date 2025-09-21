import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ballsdex.core.models import Player
from ballsdex.core.utils.logging import log_action
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.admin.coins")


class Coins(app_commands.Group):
    """
    Admin coin management commands.
    """

    def __init__(self, name: str = "coins"):
        super().__init__(name=name, description="Manage player coins")

    @app_commands.command(name="add", description="Add coins to a user's balance")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def add(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
        amount: app_commands.Range[int, 1, 10_000_000],
        reason: str | None = None,
    ):
        """
        Add coins to a user's balance.

        Parameters
        ----------
        user: discord.User
            The user to grant coins to.
        amount: int
            Amount of coins to add (must be positive).
        reason: str | None
            Optional reason for auditing.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        player, created = await Player.get_or_create(discord_id=user.id)
        before = player.coins
        await player.adjust_coins(int(amount))
        await player.refresh_from_db(fields=["coins"])  # ensure newest value

        msg = (
            f"Added {amount:,} coins to {user.mention}. Balance: {before:,} → {player.coins:,}."
        )
        if reason:
            msg += f" Reason: {reason}"

        await interaction.followup.send(msg, ephemeral=True)

        try:
            await log_action(
                f"{interaction.user} granted {amount:,} coins to {user} ({user.id})."
                + (f" Reason: {reason}" if reason else ""),
                interaction.client,
            )
        except Exception:  # logging should not block success
            log.exception("Failed to log coin grant action")

    @app_commands.command(name="remove", description="Remove coins from a user's balance")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def remove(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
        amount: app_commands.Range[int, 1, 10_000_000],
        reason: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        player, _ = await Player.get_or_create(discord_id=user.id)
        before = player.coins
        await player.adjust_coins(-int(amount))
        await player.refresh_from_db(fields=["coins"])

        msg = (
            f"Removed {amount:,} coins from {user.mention}. Balance: {before:,} → {player.coins:,}."
        )
        if reason:
            msg += f" Reason: {reason}"
        await interaction.followup.send(msg, ephemeral=True)

        try:
            await log_action(
                f"{interaction.user} removed {amount:,} coins from {user} ({user.id})."
                + (f" Reason: {reason}" if reason else ""),
                interaction.client,
            )
        except Exception:
            log.exception("Failed to log coin remove action")

    @app_commands.command(name="set", description="Set a user's coin balance to an exact value")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def set(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
        balance: app_commands.Range[int, 0, 10_000_000],
        reason: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        player, _ = await Player.get_or_create(discord_id=user.id)
        before = player.coins
        player.coins = int(balance)
        await player.save(update_fields=["coins"])
        await player.refresh_from_db(fields=["coins"])

        msg = f"Set {user.mention}'s balance: {before:,} → {player.coins:,}."
        if reason:
            msg += f" Reason: {reason}"
        await interaction.followup.send(msg, ephemeral=True)

        try:
            await log_action(
                f"{interaction.user} set coins for {user} ({user.id}) to {player.coins:,}."
                + (f" Reason: {reason}" if reason else ""),
                interaction.client,
            )
        except Exception:
            log.exception("Failed to log coin set action")

    @app_commands.command(name="balance", description="View a user's coin balance")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def balance(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User):
        await interaction.response.defer(ephemeral=True)
        player, _ = await Player.get_or_create(discord_id=user.id)
        await interaction.followup.send(
            f"{user.mention} has {player.coins:,} coins.", ephemeral=True
        )
