from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import discord
from asgiref.sync import sync_to_async
from currency_app.ledger import adjust_money
from currency_app.models import BerryTransaction, CurrencySettings, DailyBonusRole
from discord import app_commands
from discord.ext import commands
from discord.utils import format_dt
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from ballsdex.core.game_events import Event, EventContext, bus, command_did_nothing
from ballsdex.core.utils.leaderboard import EXTRA_ROWS, LEADERBOARD_SIZE, send_leaderboard
from ballsdex.core.utils.utils import can_mention, member_role_ids
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

    @app_commands.command()
    async def leaderboard(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Show the top 20 richest players.
        """
        await interaction.response.defer(thinking=True)
        holders = Player.objects.filter(money__gt=0)
        totals = await holders.aaggregate(total=Sum("money"), players=Count("id"))
        if not totals["total"]:
            await interaction.followup.send(f"Nobody has any {settings.currency_plural} yet.", ephemeral=True)
            return

        currency = settings.currency_display_plural(self.bot)
        await send_leaderboard(
            interaction,
            title=f"{(settings.currency_name or 'currency').capitalize()} Leaderboard",
            subtitle=f"Total: {totals['total']:,} {currency} owned by {totals['players']:,} players",
            ranking=[
                x
                async for x in holders.order_by("-money").values_list("discord_id", "money")[
                    : LEADERBOARD_SIZE + EXTRA_ROWS
                ]
            ],
            describe=lambda money: f"Balance: {money:,} {currency} ({money / totals['total'] * 100:.1f}% of all)",
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
        # both sides go through the ledger so the donation is traceable; the rows are already locked
        # above, so the lock adjust_money takes itself is a no-op and cannot deadlock here
        adjust_money(
            sender, -amount, reason=BerryTransaction.Reason.GIVE_SENT, description=f"Gave to {recipient.discord_id}"
        )
        adjust_money(
            recipient,
            amount,
            reason=BerryTransaction.Reason.GIVE_RECEIVED,
            description=f"Received from {sender.discord_id}",
        )
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
        bus.dispatch_soon(
            new_player.pk,
            Event.CURRENCY_RECEIVED,
            context=EventContext(partner_discord_id=interaction.user.id, received_currency=amount),
            channel_id=interaction.channel_id,
        )
        bus.dispatch_soon(
            old_player.pk,
            Event.CURRENCY_SENT,
            context=EventContext(partner_discord_id=user.id, amount=amount, server_id=interaction.guild_id),
            channel_id=interaction.channel_id,
        )

    @app_commands.command()
    async def daily(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Claim your daily payment.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        now = timezone.now()

        raw_cooldown = player.extra_data.get("berry_daily_cooldown", None)
        cooldown = datetime.fromisoformat(raw_cooldown) if raw_cooldown else None
        if cooldown is not None and cooldown >= now:
            command_did_nothing(interaction)
            await interaction.followup.send(
                f"You've already claimed the daily payment. Come back in {format_dt(cooldown, 'R')}"
            )
            return

        currency_settings = await CurrencySettings.aload()

        # streak advances if claimed again within streak_grace_hours of the last claim, else resets to day 1
        raw_last_claim = player.extra_data.get("daily_last_claim_at", None)
        last_claim = datetime.fromisoformat(raw_last_claim) if raw_last_claim else None
        if last_claim is not None and now - last_claim <= timedelta(hours=currency_settings.streak_grace_hours):
            streak_day = player.extra_data.get("daily_streak_day", 0) % 7 + 1
        else:
            streak_day = 1
        streak_bonus = getattr(currency_settings, f"day{streak_day}_reward")

        # a player with several qualifying roles gets every matching bonus added together
        matching_roles = []
        role_ids = member_role_ids(interaction.user)
        if interaction.guild_id is not None and role_ids:
            matching_roles = [
                candidate
                async for candidate in DailyBonusRole.objects.filter(
                    server__server_id=interaction.guild_id, role_id__in=role_ids
                )
            ]
        role_bonus = sum(candidate.bonus_amount for candidate in matching_roles)
        total = currency_settings.base_daily_amount + streak_bonus + role_bonus

        cooldown_end = now + timedelta(hours=24)
        player.extra_data["berry_daily_cooldown"] = cooldown_end.isoformat()
        player.extra_data["daily_last_claim_at"] = now.isoformat()
        player.extra_data["daily_streak_day"] = streak_day
        await player.add_money(
            total,
            reason=BerryTransaction.Reason.DAILY,
            description=f"Day {streak_day}/7 streak (+{streak_bonus:,} streak, +{role_bonus:,} roles)",
            server_id=interaction.guild_id,
        )
        await player.asave(update_fields=("extra_data",))
        await bus.dispatch(
            player,
            Event.CURRENCY_STREAK,
            context=EventContext(streak=streak_day, amount=total, server_id=interaction.guild_id),
            channel_id=interaction.channel_id,
        )

        emoji = settings.currency_emoji(self.bot) or settings.currency_symbol or ""
        lines = [
            f"**{currency_settings.base_daily_amount:,}** {emoji} claimed!",
            f"+{streak_bonus:,} bonus for streak - {streak_day}/7 days streak \N{FIRE}",
        ]
        for candidate in matching_roles:
            lines.append(f"+{candidate.bonus_amount:,} bonus applied for being a <@&{candidate.role_id}> supporter")
        lines.append(f"Come back tomorrow {format_dt(cooldown_end, 'R')}")

        embed = discord.Embed(description="\n".join(lines), color=settings.embed_colour)
        embed.set_footer(text=f"New balance: {player.money:,}")
        await interaction.followup.send(embed=embed)
