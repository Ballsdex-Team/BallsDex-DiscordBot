import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Optional

import discord
from achievement_app.models import AchievementType, notify_user, progress_achievement
from discord import app_commands
from discord.ext import commands
from discord.ui import Container, Section, Separator, TextDisplay, Thumbnail
from django.db.models import Q
from django.utils import timezone

from ballsdex.core.discord import LayoutView, View
from ballsdex.core.utils.menus import ChunkedListSource, ItemFormatter, Menu
from ballsdex.core.utils.transformers import BallInstanceTransform
from bd_models.models import BallInstance, Player
from settings.models import settings

from ..models import (
    BattleItem,
    BattleRecord,
    BattleSession,
    BattleSessionStatus,
    BattleSettings,
    Buff,
    Matchup,
    PlayerBattleItem,
)
from .engine import BattleAction, BattleBall, hp_bar, resolve_action

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.battle")

MAX_LOG_LINES = 5
ITEM_ACTION_FOR_EFFECT = {
    "extra_heal": BattleAction.HEAL,
    "attack_boost": BattleAction.ATTACK,
    "guaranteed_crit": BattleAction.CRIT,
}
# Same flat ATK/HP bonus per special as /boss fights (extra/... boss/cog.py's SPECIAL_BUFFS),
# keyed by the special's emoji rather than a hardcoded name so it still matches if a special is
# renamed. Field name on BattleSettings holding that bonus amount.
SPECIAL_BONUS_SETTING = {
    "⚡": "haki_special_bonus",
    "✨": "shiny_special_bonus",
    "🔮": "mythical_special_bonus",
}


def special_bonus(countryball: BallInstance, battle_settings: BattleSettings) -> int:
    special = countryball.specialcard
    if not special or not special.emoji:
        return 0
    field_name = SPECIAL_BONUS_SETTING.get(special.emoji)
    return getattr(battle_settings, field_name) if field_name else 0


async def serialize_ball(
    countryball: BallInstance, owner_id: int, bot: "BallsDexBot", battle_settings: BattleSettings
) -> BattleBall:
    buff = await Buff.aget_buff(countryball)
    ball = countryball.countryball
    emoji = bot.get_emoji(ball.emoji_id)
    bonus = special_bonus(countryball, battle_settings)
    return BattleBall(
        instance_id=countryball.pk,
        ball_id=ball.pk,
        name=ball.country,
        owner_id=owner_id,
        health=countryball.health + (buff.health if buff else 0) + bonus,
        max_health=countryball.health + (buff.health if buff else 0) + bonus,
        attack=countryball.attack + (buff.attack if buff else 0) + bonus,
        rarity=ball.rarity,
        emoji=str(emoji) if emoji else "",
        capacity_name=ball.capacity_name or "",
        capacity_logic=ball.capacity_logic or {},
    )


def side_balls(state: dict, side: str) -> list[dict]:
    return state[f"{side}_balls"]


def current_ball(state: dict, side: str) -> Optional[dict]:
    return next((b for b in side_balls(state, side) if not b["dead"]), None)


def other_side(side: str) -> str:
    return "p2" if side == "p1" else "p1"


def total_power(balls: list[dict]) -> int:
    return sum(b["attack"] + b["max_health"] for b in balls)


async def get_matchup_multiplier(attacker_ball_id: int, defender_ball_id: int) -> float:
    row = await Matchup.objects.filter(attacker_id=attacker_ball_id, defender_id=defender_ball_id).afirst()
    return row.damage_multiplier if row else 1.0


def deck_lines(balls: list[dict]) -> str:
    if not balls:
        return "Empty"
    lines = []
    for b in balls:
        if b["dead"]:
            lines.append(f"~~{b['emoji']} {b['name']}~~ 💀")
        else:
            bar = hp_bar(b["health"], b["max_health"])
            lines.append(f"{b['emoji']} {b['name']} `{bar}` {b['health']}/{b['max_health']}")
    return "\n".join(lines)


async def player_name(bot: "BallsDexBot", discord_id: int) -> str:
    user = bot.get_user(discord_id)
    if user is None:
        try:
            user = await bot.fetch_user(discord_id)
        except discord.HTTPException:
            return f"Player {discord_id}"
    return user.display_name


class BattleShopSelect(discord.ui.Select):
    def __init__(self, items: list[BattleItem]):
        options = [
            discord.SelectOption(
                label=f"{item.name} — {item.price} {settings.currency_plural}",
                description=(item.description or "")[:100],
                value=str(item.pk),
            )
            for item in items
        ]
        super().__init__(placeholder="Buy an item...", options=options)

    async def callback(self, interaction: discord.Interaction["BallsDexBot"]):
        item_id = int(self.values[0])
        try:
            item = await BattleItem.objects.aget(pk=item_id, enabled=True)
        except BattleItem.DoesNotExist:
            await interaction.response.send_message("That item is no longer available.", ephemeral=True)
            return

        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        if not player.can_afford(item.price):
            await interaction.response.send_message(
                f"You don't have enough {settings.currency_display_plural(interaction.client)} for **{item.name}**.",
                ephemeral=True,
            )
            return

        await player.remove_money(item.price)
        owned, _ = await PlayerBattleItem.objects.aget_or_create(player=player, item=item)
        owned.quantity += 1
        await owned.asave(update_fields=("quantity",))

        await interaction.response.edit_message(
            content=(
                f"Bought **{item.name}**! You now have **{owned.quantity}**.\n"
                f"Balance: {player.money} {settings.currency_display_plural(interaction.client)}"
            )
        )


class BattleShopView(View):
    def __init__(self, items: list[BattleItem]):
        super().__init__(timeout=120)
        if items:
            self.add_item(BattleShopSelect(items))


class BattleProposalView(View):
    def __init__(self, session_id: int, player1_id: int, player2_id: int):
        super().__init__(timeout=None)
        self.session_id = session_id
        self.player1_id = player1_id
        self.player2_id = player2_id

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"]) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id not in (self.player1_id, self.player2_id):
            await interaction.response.send_message("You aren't a part of this battle.", ephemeral=True)
            return False
        return True

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="✔", label="Ready")
    async def ready(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        cog: "Battle" = interaction.client.get_cog("Battle")  # type: ignore
        await cog.on_ready_click(interaction, self)

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji="✖", label="Cancel")
    async def cancel(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        cog: "Battle" = interaction.client.get_cog("Battle")  # type: ignore
        await cog.on_cancel_click(interaction, self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="🛒", label="Shop")
    async def shop(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        cog: "Battle" = interaction.client.get_cog("Battle")  # type: ignore
        await cog.open_shop(interaction)


class BattleTurnView(View):
    def __init__(self, session_id: int, active_user_id: int, other_user_id: int, capacity_label: str, timeout: int):
        super().__init__(timeout=timeout)
        self.session_id = session_id
        self.active_user_id = active_user_id
        self.other_user_id = other_user_id
        self.timed_out = False
        self.capacity.label = capacity_label[:80] or "Capacity"

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"]) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id == self.other_user_id and interaction.user.id != self.active_user_id:
            await interaction.response.send_message("It's not your turn.", ephemeral=True)
            return False
        if interaction.user.id != self.active_user_id:
            await interaction.response.send_message("You aren't a part of this battle.", ephemeral=True)
            return False
        return True

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="⚔", label="Attack")
    async def attack(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        cog: "Battle" = interaction.client.get_cog("Battle")  # type: ignore
        await cog.on_turn_action(interaction, self, BattleAction.ATTACK)

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="❤", label="Heal")
    async def heal(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        cog: "Battle" = interaction.client.get_cog("Battle")  # type: ignore
        await cog.on_turn_action(interaction, self, BattleAction.HEAL)

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji="🎲", label="Crit Gamble")
    async def crit(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        cog: "Battle" = interaction.client.get_cog("Battle")  # type: ignore
        await cog.on_turn_action(interaction, self, BattleAction.CRIT)

    @discord.ui.button(style=discord.ButtonStyle.secondary, label="Capacity")
    async def capacity(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        cog: "Battle" = interaction.client.get_cog("Battle")  # type: ignore
        await cog.on_turn_action(interaction, self, BattleAction.CAPACITY)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="🎒", label="Item")
    async def item(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        cog: "Battle" = interaction.client.get_cog("Battle")  # type: ignore
        await cog.on_item_click(interaction, self)

    @discord.ui.button(style=discord.ButtonStyle.danger, label="Forfeit", row=1)
    async def forfeit(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        cog: "Battle" = interaction.client.get_cog("Battle")  # type: ignore
        await cog.on_forfeit_click(interaction, self)

    async def on_timeout(self):
        self.timed_out = True
        cog = self._cog  # type: ignore
        await cog.on_turn_timeout(self)


class Battle(commands.GroupCog):
    """
    Brawl with your treasures!
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self._settings: BattleSettings | None = None

    async def get_settings(self, refresh: bool = True) -> BattleSettings:
        if not self._settings:
            self._settings = await BattleSettings.aload()
        if refresh:
            await self._settings.arefresh_from_db()
        return self._settings

    # -- Proposal phase -----------------------------------------------------------------

    @app_commands.command()
    async def start(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        opponent: discord.Member,
        max_size: Optional[int] = None,
        wager: app_commands.Range[int, 0] = 0,
    ):
        """
        Start a new battle with a chosen user.

        Parameters
        ----------
        opponent: discord.Member
            The player you want to battle.
        max_size: int
            How many treasures each deck can hold.
        wager: int
            Berries both players stake — winner takes all.
        """
        if opponent.bot or opponent.id == interaction.user.id:
            await interaction.response.send_message("You must pick another player.", ephemeral=True)
            return

        battle_settings = await self.get_settings()
        deck_size = max_size or battle_settings.max_deck_size
        if deck_size < 1:
            await interaction.response.send_message(
                f"You must allow at least 1 {settings.collectible_name} in the deck!", ephemeral=True
            )
            return

        player1, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        player2, _ = await Player.objects.aget_or_create(discord_id=opponent.id)

        if await self._player_is_busy(player1):
            await interaction.response.send_message("You're already in another battle right now.", ephemeral=True)
            return
        if await self._player_is_busy(player2):
            await interaction.response.send_message(
                f"{opponent.mention} is already in another battle right now.", ephemeral=True
            )
            return

        if wager and not player1.can_afford(wager):
            await interaction.response.send_message(
                f"You don't have enough {settings.currency_display_plural(self.bot)} to stake **{wager}**.",
                ephemeral=True,
            )
            return

        session = await BattleSession.objects.acreate(
            channel_id=interaction.channel_id,
            player1=player1,
            player2=player2,
            wager_amount=wager,
            status=BattleSessionStatus.PROPOSED,
            state={
                "deck_size": deck_size,
                "p1_balls": [],
                "p2_balls": [],
                "p1_ready": False,
                "p2_ready": False,
            },
        )

        embed = self.proposal_embed(session, interaction.user.display_name, opponent.display_name)
        view = BattleProposalView(session.pk, interaction.user.id, opponent.id)
        wager_text = f" for **{wager}** {settings.currency_display_plural(self.bot)}" if wager else ""
        await interaction.response.send_message(
            f"Hey {opponent.mention}, {interaction.user.mention} is proposing a battle{wager_text}!",
            embed=embed,
            view=view,
        )
        sent = await interaction.original_response()
        session.state["message_id"] = sent.id
        await session.asave(update_fields=("state",))

    def proposal_embed(self, session: BattleSession, author_name: str, opponent_name: str) -> discord.Embed:
        state = session.state
        author_ready = "✅ " if state["p1_ready"] else ""
        opponent_ready = "✅ " if state["p2_ready"] else ""
        embed = discord.Embed(
            title="Battle Plan",
            description=(
                f"Add or remove treasures with `/battle add` and `/battle remove`. Up to "
                f"**{state['deck_size']}** per deck. Click ✔ once ready — 🛒 opens the shop anytime."
            ),
            color=settings.embed_colour,
        )
        if session.wager_amount:
            embed.description += f"\n**Wager:** {session.wager_amount} {settings.currency_display_plural(self.bot)}"
        embed.add_field(name=f"{author_ready}{author_name}'s deck", value=deck_lines(state["p1_balls"]), inline=True)
        embed.add_field(
            name=f"{opponent_ready}{opponent_name}'s deck", value=deck_lines(state["p2_balls"]), inline=True
        )
        return embed

    async def _player_is_busy(self, player: Player) -> bool:
        return await BattleSession.objects.filter(
            Q(player1=player) | Q(player2=player),
            status__in=(BattleSessionStatus.PROPOSED, BattleSessionStatus.ACTIVE),
        ).aexists()

    async def get_active_session(self, interaction: discord.Interaction["BallsDexBot"]) -> BattleSession | None:
        """The battle `interaction.user` is currently a part of, if any — not scoped to a channel,
        since multiple battles can now run at once as long as they don't share a player."""
        return await BattleSession.objects.select_related("player1", "player2").filter(
            Q(player1__discord_id=interaction.user.id) | Q(player2__discord_id=interaction.user.id),
            status__in=(BattleSessionStatus.PROPOSED, BattleSessionStatus.ACTIVE),
        ).afirst()

    @app_commands.command()
    async def add(self, interaction: discord.Interaction["BallsDexBot"], countryball: BallInstanceTransform):
        """
        Add a treasure to your battle deck.
        """
        session = await self.get_active_session(interaction)
        if not session or session.status != BattleSessionStatus.PROPOSED:
            await interaction.response.send_message("You don't have a battle being set up right now!", ephemeral=True)
            return

        side = await self._side_for(session, interaction.user.id)
        if side is None:
            await interaction.response.send_message("You aren't a part of this battle!", ephemeral=True)
            return

        state = session.state
        if state[f"{side}_ready"]:
            await interaction.response.send_message(
                "You cannot change your deck, you're already ready.", ephemeral=True
            )
            return

        balls = side_balls(state, side)
        if len(balls) >= state["deck_size"]:
            await interaction.response.send_message(
                f"You cannot add more than {state['deck_size']} {settings.plural_collectible_name}!", ephemeral=True
            )
            return
        if any(b["instance_id"] == countryball.pk for b in balls):
            await interaction.response.send_message(
                f"You cannot add the same {settings.collectible_name} twice!", ephemeral=True
            )
            return

        battle_settings = await self.get_settings()
        ball = await serialize_ball(countryball, interaction.user.id, self.bot, battle_settings)
        balls.append(ball.to_dict())
        await session.asave(update_fields=("state",))

        await interaction.response.send_message(
            f"Added `{countryball.description(short=True)}`!", ephemeral=True
        )
        await self._refresh_proposal_message(interaction, session)

    @app_commands.command()
    async def remove(self, interaction: discord.Interaction["BallsDexBot"], countryball: BallInstanceTransform):
        """
        Remove a treasure from your battle deck.
        """
        session = await self.get_active_session(interaction)
        if not session or session.status != BattleSessionStatus.PROPOSED:
            await interaction.response.send_message("You don't have a battle being set up right now!", ephemeral=True)
            return

        side = await self._side_for(session, interaction.user.id)
        if side is None:
            await interaction.response.send_message("You aren't a part of this battle!", ephemeral=True)
            return

        state = session.state
        if state[f"{side}_ready"]:
            await interaction.response.send_message(
                "You cannot change your deck, you're already ready.", ephemeral=True
            )
            return

        balls = side_balls(state, side)
        before = len(balls)
        state[f"{side}_balls"] = [b for b in balls if b["instance_id"] != countryball.pk]
        if len(state[f"{side}_balls"]) == before:
            await interaction.response.send_message(
                f"That {settings.collectible_name} is not in your deck!", ephemeral=True
            )
            return

        await session.asave(update_fields=("state",))
        await interaction.response.send_message(f"Removed `{countryball.description(short=True)}`!", ephemeral=True)
        await self._refresh_proposal_message(interaction, session)

    async def _side_for(self, session: BattleSession, discord_id: int) -> str | None:
        if discord_id == session.player1.discord_id:
            return "p1"
        if discord_id == session.player2.discord_id:
            return "p2"
        return None

    async def _refresh_proposal_message(self, interaction: discord.Interaction["BallsDexBot"], session: BattleSession):
        message_id = session.state.get("message_id")
        if not message_id:
            return
        channel = self.bot.get_channel(session.channel_id) or interaction.channel
        if channel is None:
            return
        author_name = await player_name(self.bot, session.player1.discord_id)
        opponent_name = await player_name(self.bot, session.player2.discord_id)
        embed = self.proposal_embed(session, author_name, opponent_name)
        try:
            message = await channel.fetch_message(message_id)  # type: ignore
            await message.edit(embed=embed)
        except (discord.NotFound, discord.HTTPException):
            pass

    # -- Shop -----------------------------------------------------------------------------

    async def open_shop(self, interaction: discord.Interaction["BallsDexBot"]):
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        items = [x async for x in BattleItem.objects.filter(enabled=True).order_by("price")]
        owned = {
            x.item_id: x.quantity
            async for x in PlayerBattleItem.objects.filter(player=player, quantity__gt=0)
        }

        if not items:
            await interaction.response.send_message("The battle shop is empty right now.", ephemeral=True)
            return

        lines = []
        for item in items:
            have = owned.get(item.pk, 0)
            lines.append(f"**{item.name}** — {item.price} {settings.currency_display_plural(self.bot)} (own: {have})")
        content = (
            f"**Battle Shop**\nBalance: {player.money} {settings.currency_display_plural(self.bot)}\n\n"
            + "\n".join(lines)
        )
        await interaction.response.send_message(content, view=BattleShopView(items), ephemeral=True)

    # -- Proposal button handlers -----------------------------------------------------------

    async def on_ready_click(self, interaction: discord.Interaction["BallsDexBot"], view: BattleProposalView):
        session = await BattleSession.objects.select_related("player1", "player2").filter(pk=view.session_id).afirst()
        if not session or session.status != BattleSessionStatus.PROPOSED:
            await interaction.response.send_message("This battle is no longer available.", ephemeral=True)
            return

        state = session.state
        side = "p1" if interaction.user.id == view.player1_id else "p2"
        state[f"{side}_ready"] = True
        await session.asave(update_fields=("state",))

        if not (state["p1_ready"] and state["p2_ready"]):
            await interaction.response.send_message("Waiting for the other player to press Ready.", ephemeral=True)
            author_name = await player_name(self.bot, session.player1.discord_id)
            opponent_name = await player_name(self.bot, session.player2.discord_id)
            embed = self.proposal_embed(session, author_name, opponent_name)
            await interaction.message.edit(embed=embed)  # type: ignore
            return

        if not state["p1_balls"] or not state["p2_balls"]:
            state[f"{side}_ready"] = False
            await session.asave(update_fields=("state",))
            await interaction.response.send_message(
                "Both players must add at least one treasure first!", ephemeral=True
            )
            return

        await interaction.response.defer()

        if session.wager_amount:
            player1, player2 = session.player1, session.player2
            if not player1.can_afford(session.wager_amount) or not player2.can_afford(session.wager_amount):
                state["p1_ready"] = False
                state["p2_ready"] = False
                await session.asave(update_fields=("state",))
                await interaction.followup.send(
                    "One of you can no longer afford the wager. Battle not started.", ephemeral=True
                )
                return
            await player1.remove_money(session.wager_amount)
            await player2.remove_money(session.wager_amount)

        session.status = BattleSessionStatus.ACTIVE
        state["turn"] = 0
        state["active"] = "p1"
        state["log"] = []
        await session.asave(update_fields=("status", "state"))

        try:
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="Battle Plan",
                    description="Battle started! Scroll down for the fight.",
                    color=settings.embed_colour,
                ),
                view=None,
            )
        except (discord.NotFound, discord.HTTPException):
            pass

        battle_settings = await self.get_settings()
        author_name = await player_name(self.bot, session.player1.discord_id)
        opponent_name = await player_name(self.bot, session.player2.discord_id)
        embed = self.battle_embed(session, author_name, opponent_name)
        turn_view = self.build_turn_view(session, battle_settings)
        message = await interaction.followup.send(embed=embed, view=turn_view, wait=True)
        turn_view._cog = self  # type: ignore
        turn_view.message = message  # type: ignore

    async def on_cancel_click(self, interaction: discord.Interaction["BallsDexBot"], view: BattleProposalView):
        session = await BattleSession.objects.filter(pk=view.session_id).afirst()
        if not session or session.status != BattleSessionStatus.PROPOSED:
            await interaction.response.send_message("This battle is no longer available.", ephemeral=True)
            return
        session.status = BattleSessionStatus.CANCELLED
        await session.asave(update_fields=("status",))
        embed = discord.Embed(
            title="Battle Plan", description="The battle has been cancelled.", color=settings.embed_colour
        )
        try:
            await interaction.response.edit_message(embed=embed, view=None)
        except discord.InteractionResponded:
            await interaction.message.edit(embed=embed, view=None)  # type: ignore

    # -- Active battle --------------------------------------------------------------------

    def build_turn_view(self, session: BattleSession, battle_settings: BattleSettings) -> BattleTurnView:
        state = session.state
        active = state["active"]
        active_id = session.player1.discord_id if active == "p1" else session.player2.discord_id
        other_id = session.player2.discord_id if active == "p1" else session.player1.discord_id
        ball = current_ball(state, active)
        label = (ball["capacity_name"] if ball else "") or "Capacity"
        return BattleTurnView(session.pk, active_id, other_id, label, battle_settings.turn_timeout_seconds)

    def battle_embed(self, session: BattleSession, p1_name: str, p2_name: str) -> discord.Embed:
        state = session.state
        active_name = p1_name if state["active"] == "p1" else p2_name
        log_text = "\n".join(state.get("log", []))
        embed = discord.Embed(
            title="Battle in progress",
            description=f"**{active_name}**'s turn — Turn {state.get('turn', 0)}\n\n{log_text}",
            color=settings.embed_colour,
        )
        embed.add_field(name=f"{p1_name}'s deck", value=deck_lines(state["p1_balls"]), inline=True)
        embed.add_field(name=f"{p2_name}'s deck", value=deck_lines(state["p2_balls"]), inline=True)
        return embed

    async def on_turn_action(
        self, interaction: discord.Interaction["BallsDexBot"], view: BattleTurnView, action: BattleAction
    ):
        await self._resolve_and_advance(interaction, view, action, item_effect=None)

    async def on_item_click(self, interaction: discord.Interaction["BallsDexBot"], view: BattleTurnView):
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        owned = [
            x
            async for x in PlayerBattleItem.objects.filter(player=player, quantity__gt=0).select_related("item")
        ]
        if not owned:
            await interaction.response.send_message("You don't have any battle items.", ephemeral=True)
            return

        options = [
            discord.SelectOption(label=f"{x.item.name} (x{x.quantity})", value=str(x.item_id))
            for x in owned
            if x.item.effect_type in ITEM_ACTION_FOR_EFFECT
        ]
        if not options:
            await interaction.response.send_message("None of your items can be used right now.", ephemeral=True)
            return

        select = discord.ui.Select(placeholder="Use an item...", options=options)

        async def use_item(select_interaction: discord.Interaction["BallsDexBot"]):
            item_id = int(select.values[0])
            owned_item = await PlayerBattleItem.objects.select_related("item").aget(player=player, item_id=item_id)
            action = ITEM_ACTION_FOR_EFFECT[owned_item.item.effect_type]
            owned_item.quantity -= 1
            if owned_item.quantity <= 0:
                await owned_item.adelete()
            else:
                await owned_item.asave(update_fields=("quantity",))
            await select_interaction.response.defer()
            await self._resolve_and_advance(
                interaction, view, action, item_effect=(owned_item.item.effect_type, owned_item.item.effect_value)
            )

        select.callback = use_item
        item_view = View(timeout=60)
        item_view.add_item(select)
        await interaction.response.send_message(view=item_view, ephemeral=True)

    async def on_forfeit_click(self, interaction: discord.Interaction["BallsDexBot"], view: BattleTurnView):
        await interaction.response.defer()
        view.stop()
        session = await BattleSession.objects.select_related("player1", "player2").filter(pk=view.session_id).afirst()
        if not session or session.status != BattleSessionStatus.ACTIVE:
            return
        loser_side = "p1" if interaction.user.id == session.player1.discord_id else "p2"
        winner_side = other_side(loser_side)
        await self._finish_battle(interaction, session, winner_side, forfeited=True)

    async def on_turn_timeout(self, view: BattleTurnView):
        session = await BattleSession.objects.select_related("player1", "player2").filter(pk=view.session_id).afirst()
        if not session or session.status != BattleSessionStatus.ACTIVE:
            return
        message = getattr(view, "message", None)
        if message is None:
            return
        fake_interaction = None
        await self._resolve_and_advance(fake_interaction, view, BattleAction.ATTACK, item_effect=None, message=message)

    async def _resolve_and_advance(
        self,
        interaction: discord.Interaction["BallsDexBot"] | None,
        view: BattleTurnView,
        action: BattleAction,
        item_effect: tuple[str, float] | None,
        message: discord.Message | None = None,
    ):
        session = await BattleSession.objects.select_related("player1", "player2").filter(pk=view.session_id).afirst()
        if not session or session.status != BattleSessionStatus.ACTIVE:
            return
        # Stop this view now so its own timeout task can't fire again later on stale state —
        # a fresh view is always created for whichever turn comes next.
        view.stop()
        if interaction is not None:
            try:
                await interaction.response.defer()
            except discord.InteractionResponded:
                pass

        state = session.state
        active = state["active"]
        defending = other_side(active)
        attacker_ball = current_ball(state, active)
        defender_ball = current_ball(state, defending)
        if attacker_ball is None or defender_ball is None:
            return

        attacker = BattleBall.from_dict(attacker_ball)
        defender = BattleBall.from_dict(defender_ball)
        battle_settings = await self.get_settings()
        matchup = await get_matchup_multiplier(attacker.ball_id, defender.ball_id)
        result = resolve_action(action, attacker, defender, battle_settings, matchup, item_effect)

        # write mutated dataclasses back into the raw dict lists
        state[f"{active}_balls"] = [
            attacker.to_dict() if b["instance_id"] == attacker.instance_id else b for b in side_balls(state, active)
        ]
        state[f"{defending}_balls"] = [
            defender.to_dict() if b["instance_id"] == defender.instance_id else b
            for b in side_balls(state, defending)
        ]
        state["turn"] = state.get("turn", 0) + 1
        log_lines = state.setdefault("log", [])
        log_lines.append(f"Turn {state['turn']}: {result.text}")
        state["log"] = log_lines[-MAX_LOG_LINES:]

        winner_side = None
        if all(b["dead"] for b in side_balls(state, defending)):
            winner_side = active
        elif all(b["dead"] for b in side_balls(state, active)):
            winner_side = defending

        if winner_side:
            await self._finish_battle(interaction, session, winner_side, forfeited=False, message=message)
            return

        state["active"] = defending
        await session.asave(update_fields=("state",))

        p1_name = await player_name(self.bot, session.player1.discord_id)
        p2_name = await player_name(self.bot, session.player2.discord_id)
        embed = self.battle_embed(session, p1_name, p2_name)
        new_view = self.build_turn_view(session, battle_settings)
        new_view._cog = self  # type: ignore

        target_message = message or (interaction.message if interaction else None)
        if target_message is not None:
            edited = await target_message.edit(embed=embed, view=new_view)
            new_view.message = edited  # type: ignore
        elif interaction is not None:
            edited = await interaction.edit_original_response(embed=embed, view=new_view)
            new_view.message = edited  # type: ignore

    async def _finish_battle(
        self,
        interaction: discord.Interaction["BallsDexBot"] | None,
        session: BattleSession,
        winner_side: str,
        forfeited: bool,
        message: discord.Message | None = None,
    ):
        state = session.state
        loser_side = other_side(winner_side)
        winner_player = session.player1 if winner_side == "p1" else session.player2
        loser_player = session.player2 if winner_side == "p1" else session.player1

        session.status = BattleSessionStatus.FINISHED
        await session.asave(update_fields=("status", "state"))

        wager_paid = 0
        if session.wager_amount:
            wager_paid = session.wager_amount * 2
            await winner_player.add_money(wager_paid)

        earnings = await self._compute_earnings(
            winner_player, loser_player, side_balls(state, winner_side), side_balls(state, loser_side)
        )
        if earnings:
            await winner_player.add_money(earnings)

        await BattleRecord.objects.acreate(
            player1=session.player1,
            player2=session.player2,
            winner=winner_player,
            wager_amount=session.wager_amount,
            winner_earnings=earnings,
            turns=state.get("turn", 0),
        )

        p1_name = await player_name(self.bot, session.player1.discord_id)
        p2_name = await player_name(self.bot, session.player2.discord_id)
        winner_name = p1_name if winner_side == "p1" else p2_name

        embed = discord.Embed(title="Battle: Complete!", color=settings.embed_colour)
        forfeit_suffix = " (forfeit)" if forfeited else ""
        summary = f"**Winner: {winner_name}**{forfeit_suffix}\nTurns: {state.get('turn', 0)}"
        if session.wager_amount:
            summary += f"\nWager won: {wager_paid} {settings.currency_display_plural(self.bot)}"
        if earnings:
            summary += f"\nBattle reward: {earnings} {settings.currency_display_plural(self.bot)}"
        embed.description = summary
        embed.add_field(name=f"{p1_name}'s final deck", value=deck_lines(state["p1_balls"]), inline=True)
        embed.add_field(name=f"{p2_name}'s final deck", value=deck_lines(state["p2_balls"]), inline=True)

        target_message = message or (interaction.message if interaction else None)
        try:
            if target_message is not None:
                await target_message.edit(embed=embed, view=None)
            elif interaction is not None:
                await interaction.edit_original_response(embed=embed, view=None)
        except (discord.NotFound, discord.HTTPException):
            pass

        unlocked = await progress_achievement(winner_player, AchievementType.FIRST_BATTLE_WIN)
        winner_user = self.bot.get_user(winner_player.discord_id)
        if winner_user:
            await notify_user(unlocked, user=winner_user, channel=target_message.channel if target_message else None)

    async def _compute_earnings(
        self, winner: Player, loser: Player, winner_balls: list[dict], loser_balls: list[dict]
    ) -> int:
        battle_settings = await self.get_settings()
        since = timezone.now() - timedelta(hours=24)
        wins_today = await BattleRecord.objects.filter(winner=winner, created_at__gte=since).acount()
        same_opponent_wins = await BattleRecord.objects.filter(
            winner=winner, created_at__gte=since
        ).filter(Q(player1=loser) | Q(player2=loser)).acount()

        if same_opponent_wins >= battle_settings.max_rewarded_wins_per_opponent_per_day:
            return 0

        if wins_today < battle_settings.guaranteed_daily_wins:
            return battle_settings.guaranteed_win_reward

        winner_power = max(1, total_power(winner_balls))
        loser_power = total_power(loser_balls)
        scale = min(
            battle_settings.performance_scale_max,
            max(battle_settings.performance_scale_min, loser_power / winner_power),
        )
        return round(battle_settings.performance_base_reward * scale)

    # -- Leaderboard ------------------------------------------------------------------------

    @app_commands.command()
    async def leaderboard(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Show the top 10 players by battle wins.
        """
        await interaction.response.defer(thinking=True)

        wins_by_player: dict[int, int] = {}
        games_by_player: dict[int, int] = {}
        async for record in BattleRecord.objects.all().only("player1_id", "player2_id", "winner_id"):
            games_by_player[record.player1_id] = games_by_player.get(record.player1_id, 0) + 1
            games_by_player[record.player2_id] = games_by_player.get(record.player2_id, 0) + 1
            if record.winner_id:
                wins_by_player[record.winner_id] = wins_by_player.get(record.winner_id, 0) + 1

        if not wins_by_player:
            await interaction.followup.send("No battles have been recorded yet.", ephemeral=True)
            return

        top = sorted(wins_by_player.items(), key=lambda x: x[1], reverse=True)[:10]
        players = {p.pk: p async for p in Player.objects.filter(id__in=[pk for pk, _ in top])}

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        entries = []
        for rank, (player_id, wins) in enumerate(top, start=1):
            player = players.get(player_id)
            if not player:
                continue
            games = games_by_player.get(player_id, wins)
            win_rate = round(wins / games * 100, 1) if games else 0.0
            try:
                user = await self.bot.fetch_user(player.discord_id)
            except (discord.NotFound, discord.HTTPException):
                continue
            entries.append(
                Section(
                    TextDisplay(
                        f"### {medals.get(rank, rank)}\n"
                        f"> {user.display_name}\n> Wins: {wins} • Games: {games} • Win rate: {win_rate}%"
                    ),
                    accessory=Thumbnail(media=user.display_avatar.url),
                )
            )

        view = LayoutView()
        view.restrict_author(interaction.user.id)
        container = Container(TextDisplay(f"# {settings.bot_name} Battle Leaderboard"), Separator())
        view.add_item(container)
        menu = Menu(interaction.client, view, ChunkedListSource(entries, 3), ItemFormatter(container, 2))
        await menu.init()
        await interaction.followup.send(view=view, allowed_mentions=discord.AllowedMentions(users=False))
