"""
Definition of every quest type: which events make it progress, which settings it uses, which package it needs and
how its goal is written for players.

Adding a quest type means adding a `TypeDefinition` here and a branch in `engine._evaluate`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ballsdex.core.game_events import Event
from settings.models import settings

from .integrations import AUCTION_HOUSE, BATTLES, CRAFTING, MERCHANT, PACKS, Integration
from .models import Measure, Quest, QuestType

TREASURE_FILTERS = (
    "ball",
    "special",
    "any_special",
    "group",
    "min_rarity",
    "max_rarity",
    "min_attack_bonus",
    "min_health_bonus",
    "hex_contains",
)
BERRY_MEASURES = (Measure.COUNT, Measure.AMOUNT)


@dataclass(frozen=True)
class TypeDefinition:
    type: QuestType
    events: frozenset[Event]
    fields: tuple[str, ...]
    goal_label: str
    help: str
    describe: Callable[[Quest], str]
    measures: tuple[Measure, ...] = (Measure.COUNT,)
    integration: Integration | None = None
    # whether the treasure filters apply to the treasures carried by the event
    filters_instances: bool = True


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def _berries(amount: int) -> str:
    return f"{amount:,} {settings.currency_plural}"


def _treasures(quest: Quest, count: int) -> str:
    """
    "5 Shiny Monkey D. Luffy treasures", "a treasure with a special", "one treasure of the Straw Hats group"...
    """
    words = []
    if quest.cached_special:
        words.append(quest.cached_special.name)
    if quest.cached_ball:
        words.append(quest.cached_ball.country)
    name = _plural(count, settings.collectible_name, settings.plural_collectible_name)
    text = f"{count if count > 1 else 'a'} {' '.join(words + [name])}"
    if quest.any_special and not quest.cached_special:
        text += " with a special"
    if quest.cached_group:
        text += f" from the {quest.cached_group.name} group"
    # a lower rarity value is a rarer treasure, and players call a treasure of rarity 60 a "T60"
    if quest.min_rarity is not None and quest.max_rarity is not None:
        text += f" between T{quest.min_rarity:g} and T{quest.max_rarity:g}"
    elif quest.max_rarity is not None:
        text += f" of T{quest.max_rarity:g} or rarer"
    elif quest.min_rarity is not None:
        text += f" of T{quest.min_rarity:g} or more common"
    if quest.min_attack_bonus is not None or quest.min_health_bonus is not None:
        stats = []
        if quest.min_attack_bonus is not None:
            stats.append(f"{quest.min_attack_bonus:+d}% attack")
        if quest.min_health_bonus is not None:
            stats.append(f"{quest.min_health_bonus:+d}% health")
        text += f" with at least {' and '.join(stats)}"
    if quest.hex_contains:
        text += f' whose ID contains "{quest.hex_contains.upper()}"'
    return text


def _where(quest: Quest) -> str:
    return " in the main server" if quest.main_server_only else ""


def _with(quest: Quest) -> str:
    return f" with <@{quest.partner_discord_id}>" if quest.partner_discord_id else ""


def _times(count: int) -> str:
    return f" {count} times" if count > 1 else ""


def _describe_catch(quest: Quest) -> str:
    text = f"Catch {_treasures(quest, quest.target)}{_where(quest)}"
    if quest.max_catch_seconds is not None:
        text += f" in less than {quest.max_catch_seconds:g} seconds"
    return f"{text}."


def _describe_obtain(quest: Quest) -> str:
    return f"Obtain {_treasures(quest, quest.target)}{_where(quest)}."


def _describe_currency_streak(quest: Quest) -> str:
    return f"Claim your daily {settings.currency_plural} {quest.target} days in a row."


def _describe_pack_streak(quest: Quest) -> str:
    return f"Claim your daily pack {quest.target} days in a row."


def _describe_command(quest: Quest) -> str:
    return f"Use /{quest.command_name or '?'}{_times(quest.target)}{_where(quest)}."


def _describe_trade(quest: Quest) -> str:
    count = quest.target
    text = f"Complete {count if count > 1 else 'a'} {_plural(count, 'trade')}{_with(quest)}"
    conditions = []
    if quest.must_receive_treasure or quest.ball_id or quest.special_id or quest.any_special:
        conditions.append(_treasures(quest, 1))
    if quest.min_currency:
        conditions.append(f"at least {_berries(quest.min_currency)}")
    if conditions:
        text += f" where you receive {' and '.join(conditions)}"
    return f"{text}."


def _describe_trade_treasures(quest: Quest) -> str:
    treasures = _plural(quest.target, settings.collectible_name, settings.plural_collectible_name)
    return f"Exchange {quest.target} {treasures} in {'a single trade' if quest.in_one_trade else 'trades'}."


def _describe_give_treasures(quest: Quest) -> str:
    recipient = f"<@{quest.partner_discord_id}>" if quest.partner_discord_id else "other players"
    return f"Give {_treasures(quest, quest.target)} to {recipient}{_where(quest)}."


def _describe_friend(quest: Quest) -> str:
    if quest.partner_discord_id:
        return f"Become friends with <@{quest.partner_discord_id}>."
    count = quest.target
    return f"Add {count} new {_plural(count, 'friend')}."


def _describe_battle(quest: Quest) -> str:
    count = quest.target
    return f"Win {count if count > 1 else 'a'} {_plural(count, 'battle')}."


def _describe_give(quest: Quest) -> str:
    if quest.measure == Measure.AMOUNT:
        return f"Give {_berries(quest.target)} to other players{_with(quest)}."
    minimum = f" of at least {_berries(quest.min_currency)}" if quest.min_currency else ""
    count = quest.target
    return f"Give berries{minimum} to other players{_with(quest)}{_times(count)}."


def _describe_receive(quest: Quest) -> str:
    if quest.measure == Measure.AMOUNT:
        return f"Receive {_berries(quest.target)} from other players{_with(quest)}."
    minimum = f" of at least {_berries(quest.min_currency)}" if quest.min_currency else ""
    return f"Receive berries{minimum} from other players{_with(quest)}{_times(quest.target)}."


def _describe_catch_currency(quest: Quest) -> str:
    if quest.measure == Measure.AMOUNT:
        return f"Earn {_berries(quest.target)} by catching {settings.plural_collectible_name}{_where(quest)}."
    count = quest.target
    return f"Get berries from a catch{_times(count)}{_where(quest)}."


def _describe_spend(quest: Quest) -> str:
    if quest.measure == Measure.AMOUNT:
        return f"Spend {_berries(quest.target)}."
    return f"Spend berries{_times(quest.target)}."


def _describe_craft(quest: Quest) -> str:
    kind = quest.tier_level.name.lower() if quest.tier_level_id and quest.tier_level else ""
    what = f"{kind} " if kind else ""
    if quest.collector_id and quest.collector:
        return f"Craft the {what}card of {quest.collector.name}{_times(quest.target)}."
    count = quest.target
    return f"Craft {count if count > 1 else 'a'} {what}{_plural(count, 'card')}."


def _describe_pack(quest: Quest) -> str:
    if quest.measure == Measure.AMOUNT:
        return f"Spend {_berries(quest.target)} on packs."
    name = quest.item.name if quest.item_id and quest.item else "pack"
    count = quest.target
    return f"Buy {count} {_plural(count, name)}."


def _describe_merchant(quest: Quest) -> str:
    if quest.measure == Measure.AMOUNT:
        return f"Spend {_berries(quest.target)} at the merchant."
    if quest.merchant_item_id and quest.merchant_item:
        return f"Buy {quest.merchant_item.name} from the merchant{_times(quest.target)}."
    count = quest.target
    return f"Buy {count} {_plural(count, 'item')} from the merchant."


def _describe_shop(quest: Quest) -> str:
    if quest.measure == Measure.AMOUNT:
        return f"Spend {_berries(quest.target)} in Buggy's shop."
    return f"Buy {_treasures(quest, quest.target)} from Buggy's shop."


def _describe_sell(quest: Quest) -> str:
    if quest.measure == Measure.AMOUNT:
        return f"Earn {_berries(quest.target)} by selling to Buggy."
    return f"Sell {_treasures(quest, quest.target)} to Buggy."


def _describe_auction_create(quest: Quest) -> str:
    return f"List {_treasures(quest, quest.target)} on the auction house."


def _describe_auction_bid(quest: Quest) -> str:
    if quest.measure == Measure.AMOUNT:
        return f"Bid {_berries(quest.target)} on the auction house."
    minimum = f" of at least {_berries(quest.min_currency)}" if quest.min_currency else ""
    count = quest.target
    return f"Place {count} {_plural(count, 'bid')}{minimum} on the auction house."


def _describe_auction_won(quest: Quest) -> str:
    if quest.measure == Measure.AMOUNT:
        return f"Win {_berries(quest.target)} worth of auctions."
    count = quest.target
    return f"Win {count} {_plural(count, 'auction')}."


TYPES: dict[str, TypeDefinition] = {
    definition.type: definition
    for definition in (
        TypeDefinition(
            QuestType.CATCH,
            frozenset({Event.CATCH}),
            TREASURE_FILTERS + ("main_server_only", "max_catch_seconds"),
            "Number of catches",
            "Counts the treasures the player catches themselves when they spawn.",
            _describe_catch,
        ),
        TypeDefinition(
            QuestType.OBTAIN,
            frozenset({Event.CATCH, Event.OBTAIN}),
            TREASURE_FILTERS + ("main_server_only",),
            "Number of treasures obtained",
            "Counts the treasures the player gets in any way: catches, trades, packs, crafts, rewards...",
            _describe_obtain,
        ),
        TypeDefinition(
            QuestType.COMMAND,
            frozenset({Event.COMMAND}),
            ("command_name", "require_command_effect", "main_server_only"),
            "Number of uses",
            'Counts the uses of one slash command, like "treasures list" to open the inventory.',
            _describe_command,
            filters_instances=False,
        ),
        TypeDefinition(
            QuestType.TRADE,
            frozenset({Event.TRADE}),
            ("partner_discord_id", "min_currency", "must_receive_treasure", "ball", "special", "any_special"),
            "Number of trades",
            "Counts completed trades. The treasure filters apply to what the player receives.",
            _describe_trade,
        ),
        TypeDefinition(
            QuestType.TRADE_TREASURES,
            frozenset({Event.TRADE}),
            ("in_one_trade", "partner_discord_id"),
            "Number of treasures exchanged",
            "Counts the treasures changing hands in the player's trades, given and received. A trade where only "
            "one side gives something is a gift and doesn't count.",
            _describe_trade_treasures,
            filters_instances=False,
        ),
        TypeDefinition(
            QuestType.GIVE_TREASURES,
            frozenset({Event.GIFT}),
            TREASURE_FILTERS + ("partner_discord_id", "main_server_only"),
            "Number of treasures given",
            "Counts the treasures the player gives away with the give command. Set a partner to ask for a present "
            "to one person in particular.",
            _describe_give_treasures,
        ),
        TypeDefinition(
            QuestType.FRIEND,
            frozenset({Event.FRIEND}),
            ("partner_discord_id",),
            "Number of new friends",
            "Counts the friendships made during the event, not the ones the player already had.",
            _describe_friend,
            filters_instances=False,
        ),
        TypeDefinition(
            QuestType.BATTLE_WIN,
            frozenset({Event.BATTLE_WIN}),
            (),
            "Number of battles won",
            "Counts the battles the player wins.",
            _describe_battle,
            integration=BATTLES,
            filters_instances=False,
        ),
        TypeDefinition(
            QuestType.GIVE_CURRENCY,
            frozenset({Event.CURRENCY_SENT}),
            ("partner_discord_id", "min_currency"),
            "Number of gifts, or berries given",
            "Counts the berries the player gives away with the give command.",
            _describe_give,
            measures=BERRY_MEASURES,
            filters_instances=False,
        ),
        TypeDefinition(
            QuestType.RECEIVE_CURRENCY,
            frozenset({Event.CURRENCY_RECEIVED}),
            ("partner_discord_id", "min_currency"),
            "Number of gifts, or berries received",
            "Counts the berries the player receives from someone, a player or an admin.",
            _describe_receive,
            measures=BERRY_MEASURES,
            filters_instances=False,
        ),
        TypeDefinition(
            QuestType.CATCH_CURRENCY,
            frozenset({Event.CATCH_REWARD}),
            TREASURE_FILTERS + ("main_server_only",),
            "Number of catches with berries, or berries earned",
            "Counts the times a catch also gives berries, or how many berries those catches gave.",
            _describe_catch_currency,
            measures=BERRY_MEASURES,
        ),
        TypeDefinition(
            QuestType.CURRENCY_STREAK,
            frozenset({Event.CURRENCY_STREAK}),
            ("main_server_only",),
            "Days in a row",
            "Counts the streak of daily berry claims the player is on, not how many times they claimed. "
            "A streak that breaks starts the count again.",
            _describe_currency_streak,
            filters_instances=False,
        ),
        TypeDefinition(
            QuestType.PACK_STREAK,
            frozenset({Event.PACK_STREAK}),
            ("main_server_only",),
            "Days in a row",
            "Counts the streak of daily pack claims the player is on. A streak that breaks starts again.",
            _describe_pack_streak,
            filters_instances=False,
        ),
        TypeDefinition(
            QuestType.SPEND_CURRENCY,
            frozenset({Event.ECONOMY}),
            (),
            "Number of purchases, or berries spent",
            "Counts every berry the player spends, wherever they spend it.",
            _describe_spend,
            measures=BERRY_MEASURES,
            filters_instances=False,
        ),
        TypeDefinition(
            QuestType.CRAFT,
            frozenset({Event.CRAFT}),
            ("collector", "tier_level"),
            "Number of crafts",
            'Counts the collector cards the player claims. Pick a craft type ("Craft", "Elemental") to only count '
            "those, and a collector to ask for one card in particular.",
            _describe_craft,
            integration=CRAFTING,
            filters_instances=False,
        ),
        TypeDefinition(
            QuestType.PACK_BUY,
            frozenset({Event.PACK_BUY}),
            ("item",),
            "Number of packs, or berries spent",
            "Counts the packs the player buys.",
            _describe_pack,
            measures=BERRY_MEASURES,
            integration=PACKS,
            filters_instances=False,
        ),
        TypeDefinition(
            QuestType.MERCHANT_BUY,
            frozenset({Event.MERCHANT_BUY}),
            ("merchant_item",),
            "Number of purchases, or berries spent",
            "Counts what the player buys from the merchant.",
            _describe_merchant,
            measures=BERRY_MEASURES,
            integration=MERCHANT,
            filters_instances=False,
        ),
        TypeDefinition(
            QuestType.SHOP_BUY,
            frozenset({Event.SHOP_BUY}),
            TREASURE_FILTERS,
            "Number of purchases, or berries spent",
            "Counts the treasures the player buys from Buggy's shop. Use the rarity filters to ask for treasures "
            "of a given tier.",
            _describe_shop,
            measures=BERRY_MEASURES,
            integration=AUCTION_HOUSE,
        ),
        TypeDefinition(
            QuestType.SELL,
            frozenset({Event.SELL}),
            TREASURE_FILTERS,
            "Number of sales, or berries earned",
            "Counts the treasures the player sells to Buggy. Use the rarity filters to ask for treasures of a "
            "given tier.",
            _describe_sell,
            measures=BERRY_MEASURES,
            integration=AUCTION_HOUSE,
        ),
        TypeDefinition(
            QuestType.AUCTION_CREATE,
            frozenset({Event.AUCTION_CREATE}),
            TREASURE_FILTERS,
            "Number of listings",
            "Counts the treasures the player puts up for auction.",
            _describe_auction_create,
            integration=AUCTION_HOUSE,
        ),
        TypeDefinition(
            QuestType.AUCTION_BID,
            frozenset({Event.AUCTION_BID}),
            ("min_currency",),
            "Number of bids, or berries bid",
            "Counts the bids that went through. Raising a bid already placed doesn't count again.",
            _describe_auction_bid,
            measures=BERRY_MEASURES,
            integration=AUCTION_HOUSE,
            filters_instances=False,
        ),
        TypeDefinition(
            QuestType.AUCTION_WON,
            frozenset({Event.AUCTION_WON}),
            TREASURE_FILTERS,
            "Number of auctions won, or berries paid",
            "Counts the listings the player wins, when the seller accepts their bid.",
            _describe_auction_won,
            measures=BERRY_MEASURES,
            integration=AUCTION_HOUSE,
        ),
    )
}

PARAMETER_FIELDS = tuple(dict.fromkeys(name for definition in TYPES.values() for name in definition.fields))


def goal_text(quest: Quest) -> str:
    definition = TYPES.get(quest.type)
    return definition.describe(quest) if definition else ""


def player_description(quest: Quest) -> str:
    return quest.description or goal_text(quest)
