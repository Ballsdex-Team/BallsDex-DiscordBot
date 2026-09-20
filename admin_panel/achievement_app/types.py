"""
Definition of every achievement type: which events make it progress, which settings it uses and how its goal is
described to players.
"""

from collections.abc import Callable
from dataclasses import dataclass

from ballsdex.core.game_events import ACTIVITY_EVENTS, Event
from settings.models import settings

from .models import Achievement, AchievementType, TimeUnit

TREASURE_FILTERS = ("ball", "special", "any_special", "group", "min_attack_bonus", "min_health_bonus", "hex_contains")


@dataclass(frozen=True)
class TypeDefinition:
    type: AchievementType
    events: frozenset[Event]
    fields: tuple[str, ...]
    goal_label: str
    help: str
    describe: Callable[[Achievement], str]


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def _treasures(achievement: Achievement, count: int) -> str:
    """
    "5 Shiny Monkey D. Luffy treasures", "a treasure with a special", "one treasure of the Straw Hats group"...
    """
    words = []
    if achievement.cached_special:
        words.append(achievement.cached_special.name)
    if achievement.cached_ball:
        words.append(achievement.cached_ball.country)
    name = _plural(count, settings.collectible_name, settings.plural_collectible_name)
    text = f"{count if count > 1 else 'a'} {' '.join(words + [name])}"
    if achievement.any_special and not achievement.cached_special:
        text += " with a special"
    if achievement.cached_group:
        text += f" from the {achievement.cached_group.name} group"
    if achievement.min_attack_bonus is not None or achievement.min_health_bonus is not None:
        stats = []
        if achievement.min_attack_bonus is not None:
            stats.append(f"{achievement.min_attack_bonus:+d}% attack")
        if achievement.min_health_bonus is not None:
            stats.append(f"{achievement.min_health_bonus:+d}% health")
        text += f" with at least {' and '.join(stats)}"
    if achievement.hex_contains:
        text += f' whose ID contains "{achievement.hex_contains.upper()}"'
    return text


def _describe_catch(achievement: Achievement) -> str:
    text = f"Catch {_treasures(achievement, achievement.target_value)}"
    if achievement.server_id:
        text += " in the main server"
    if achievement.max_catch_seconds is not None:
        text += f" in less than {achievement.max_catch_seconds:g} seconds"
    return f"{text}."


def _describe_obtain(achievement: Achievement) -> str:
    return f"Obtain {_treasures(achievement, achievement.target_value)}."


def _describe_own(achievement: Achievement) -> str:
    return f"Own {_treasures(achievement, achievement.target_value)} at the same time."


def _describe_group(achievement: Achievement) -> str:
    group = achievement.cached_group
    return f"Own one of each {settings.collectible_name} of the {group.name if group else '?'} group."


def _describe_completion(achievement: Achievement) -> str:
    return f"Reach {achievement.target_value}% completion."


def _describe_trade(achievement: Achievement) -> str:
    count = achievement.target_value
    text = f"Complete {count if count > 1 else 'a'} {_plural(count, 'trade')}"
    if achievement.partner_discord_id:
        text += f" with <@{achievement.partner_discord_id}>"
    conditions = []
    if achievement.must_receive_treasure or achievement.ball_id or achievement.special_id:
        conditions.append(_treasures(achievement, 1))
    if achievement.min_currency:
        conditions.append(f"at least {achievement.min_currency:,} {settings.currency_plural}")
    if conditions:
        text += f" where you receive {' and '.join(conditions)}"
    return f"{text}."


def _describe_trade_treasures(achievement: Achievement) -> str:
    count = achievement.target_value
    treasures = _plural(count, settings.collectible_name, settings.plural_collectible_name)
    return f"Exchange {count} {treasures} in {'a single trade' if achievement.in_one_trade else 'trades'}."


def _describe_friends(achievement: Achievement) -> str:
    count = achievement.target_value
    return f"Have {count} {_plural(count, 'friend')}."


def _describe_favorites(achievement: Achievement) -> str:
    count = achievement.target_value
    return f"Have {count} favorite {_plural(count, settings.collectible_name, settings.plural_collectible_name)}."


def _describe_battle(achievement: Achievement) -> str:
    count = achievement.target_value
    return f"Win {count if count > 1 else 'a'} {_plural(count, 'battle')}."


def _describe_command(achievement: Achievement) -> str:
    count = achievement.target_value
    return f"Use /{achievement.command_name or '?'}{f' {count} times' if count > 1 else ''}."


def _describe_receive_currency(achievement: Achievement) -> str:
    count = achievement.target_value
    amount = f"at least {achievement.min_currency:,} " if achievement.min_currency else ""
    text = f"Receive {amount}{settings.currency_plural}"
    if achievement.partner_discord_id:
        text += f" from <@{achievement.partner_discord_id}>"
    return f"{text}{f' {count} times' if count > 1 else ''}."


def _describe_playtime(achievement: Achievement) -> str:
    count = achievement.target_value
    unit = TimeUnit(achievement.time_unit).label.lower()
    return f"Play for {count} {unit.removesuffix('s') if count == 1 else unit} since your first catch."


TYPES: dict[str, TypeDefinition] = {
    definition.type: definition
    for definition in (
        TypeDefinition(
            AchievementType.CATCH,
            frozenset({Event.CATCH}),
            TREASURE_FILTERS + ("server_id", "max_catch_seconds"),
            "Number of catches",
            "Counts the treasures the player catches themselves when they spawn. Use it for first catches, "
            "catching a special, catching fast or catching in the main server.",
            _describe_catch,
        ),
        TypeDefinition(
            AchievementType.OBTAIN,
            frozenset({Event.CATCH, Event.OBTAIN}),
            TREASURE_FILTERS + ("server_id",),
            "Number of treasures obtained",
            "Counts the treasures the player gets in any way: catches, trades, donations, packs, collector cards, "
            "rewards... Treasures given away and received again count again.",
            _describe_obtain,
        ),
        TypeDefinition(
            AchievementType.OWN,
            frozenset({Event.CATCH, Event.OBTAIN, Event.SYNC}),
            TREASURE_FILTERS,
            "Number of treasures owned",
            "Checked when the player gets a matching treasure: unlocked once they own that many at the same time.",
            _describe_own,
        ),
        TypeDefinition(
            AchievementType.COMPLETE_GROUP,
            frozenset({Event.CATCH, Event.OBTAIN, Event.SYNC}),
            ("group",),
            "Number of different treasures of the group (leave 0 for the whole group)",
            "Unlocked once the player owns one of each treasure of the group.",
            _describe_group,
        ),
        TypeDefinition(
            AchievementType.COMPLETION,
            frozenset({Event.CATCH, Event.OBTAIN, Event.SYNC}),
            (),
            "Completion percentage (200 = two of each)",
            "Percentage of the enabled treasures owned. Above 100, 200% means owning two of each treasure.",
            _describe_completion,
        ),
        TypeDefinition(
            AchievementType.TRADE,
            frozenset({Event.TRADE}),
            ("partner_discord_id", "min_currency", "must_receive_treasure", "ball", "special", "any_special"),
            "Number of trades",
            "Counts the trades completed with /trade. Treasure filters apply to the treasures received.",
            _describe_trade,
        ),
        TypeDefinition(
            AchievementType.TRADE_TREASURES,
            frozenset({Event.TRADE}),
            ("in_one_trade",),
            "Number of treasures",
            "Counts the treasures changing hands in the player's trades, given and received. A trade where only one "
            "side gives something is a gift and doesn't count. Past trades are counted with the recompute action.",
            _describe_trade_treasures,
        ),
        TypeDefinition(
            AchievementType.FRIENDS,
            frozenset({Event.FRIEND, Event.SYNC}),
            (),
            "Number of friends",
            "Checked when the player adds a friend.",
            _describe_friends,
        ),
        TypeDefinition(
            AchievementType.FAVORITES,
            frozenset({Event.FAVORITE, Event.SYNC}),
            (),
            "Number of favorite treasures",
            "Checked when the player sets a favorite treasure.",
            _describe_favorites,
        ),
        TypeDefinition(
            AchievementType.BATTLE_WIN,
            frozenset({Event.BATTLE_WIN}),
            (),
            "Number of battles won",
            "Counts the battles won.",
            _describe_battle,
        ),
        TypeDefinition(
            AchievementType.COMMAND,
            frozenset({Event.COMMAND}),
            ("command_name",),
            "Number of uses",
            'Counts the uses of a slash command, like "treasures list" to open the inventory. The uses from before '
            "the achievement is published are not known.",
            _describe_command,
        ),
        TypeDefinition(
            AchievementType.RECEIVE_CURRENCY,
            frozenset({Event.CURRENCY_RECEIVED}),
            ("partner_discord_id", "min_currency"),
            "Number of gifts received",
            "Counts the times the player receives currency from someone, with the give command or the admin add "
            "command. Set the giver's Discord ID to make one achievement per admin.",
            _describe_receive_currency,
        ),
        TypeDefinition(
            AchievementType.PLAYTIME,
            ACTIVITY_EVENTS,
            ("time_unit",),
            "Time played, in the unit chosen below",
            "Counted from the first treasure the player caught themselves, checked whenever they do something.",
            _describe_playtime,
        ),
    )
}

PARAMETER_FIELDS = tuple(dict.fromkeys(field for definition in TYPES.values() for field in definition.fields))


def goal_text(achievement: Achievement) -> str:
    definition = TYPES.get(achievement.type)
    return definition.describe(achievement) if definition else ""


def player_description(achievement: Achievement) -> str:
    return achievement.description or goal_text(achievement)
