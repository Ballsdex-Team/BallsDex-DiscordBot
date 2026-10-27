from typing import TYPE_CHECKING

import discord
from asgiref.sync import sync_to_async
from discord import app_commands
from discord.ext import commands
from django.db import transaction
from django.db.models import F

from ballsdex.core.utils.utils import can_mention
from bd_models.models import Player, Trade
from settings.models import settings
from settings.utils import format_currency

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class NotEnoughMoney(RuntimeError):
    """
    The sender's balance dropped below the donated amount before the transaction locked it.
    """


class Money(commands.GroupCog):
    """
    Currency commands
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    async def balance(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check your balance.
        """
        try:
            player = await Player.objects.aget(discord_id=interaction.user.id)
        except Player.DoesNotExist:
            balance = 0
        else:
            balance = player.money
        await interaction.response.send_message(
            f"You have {format_currency(balance, shortened=False, bot=self.bot)}.", ephemeral=True
        )

    @transaction.atomic()
    def perform_donation(self, old_player: Player, new_player: Player, amount: int) -> Trade:
        # a plain refresh does not lock, so two concurrent donations could both pass the check
        # below and overdraw the account. Ordering by primary key keeps two players donating to
        # each other from deadlocking.
        locked = {
            player.pk: player
            for player in Player.objects.select_for_update()
            .filter(pk__in=(old_player.pk, new_player.pk))
            .order_by("pk")
        }
        sender, recipient = locked[old_player.pk], locked[new_player.pk]
        if not sender.can_afford(amount):
            raise NotEnoughMoney(f"Player's balance changed, cannot afford donation anymore {amount=} {sender.money=}")
        sender.money = F("money") - amount
        recipient.money = F("money") + amount
        sender.save(update_fields=["money"])
        recipient.save(update_fields=["money"])
        return Trade.objects.create(player1=sender, player2=recipient, player1_money=amount)

    @app_commands.command()
    async def give(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User, amount: int):
        """
        Give money to a player.

        Parameters
        ----------
        user: discord.User
            The player you want to give money to.
        amount: int
            The amount to give.
        """
        if amount < 1:
            await interaction.response.send_message("Amount must be strictly positive.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("You cannot donate to bots.", ephemeral=True)
            return
        if user == interaction.user:
            await interaction.response.send_message(
                f"You cannot give {settings.currency_display_plural(self.bot)} to yourself.", ephemeral=True
            )
            return

        await interaction.response.defer()
        old_player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        if not old_player.can_afford(amount):
            await interaction.followup.send(
                f"You do not have enough {settings.currency_display_plural(self.bot)}.", ephemeral=True
            )
            return

        new_player, _ = await Player.objects.aget_or_create(discord_id=user.id)
        blocked = await new_player.is_blocked(old_player)
        if blocked:
            await interaction.followup.send("You cannot interact with a user that has blocked you.", ephemeral=True)
            return
        if new_player.discord_id in self.bot.blacklist:
            await interaction.followup.send("You cannot donate to a blacklisted user.", ephemeral=True)
            return

        try:
            await sync_to_async(self.perform_donation)(old_player, new_player, amount)
        except NotEnoughMoney:
            await interaction.followup.send(
                f"Your balance changed, you do not have enough {settings.currency_display_plural(self.bot)} anymore.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            f"You just gave {format_currency(amount, bot=self.bot)} to {user.mention}!",
            allowed_mentions=await can_mention([new_player]),
        )
