import discord
from discord.ext.commands import FlagConverter, Range, flag

from ballsdex.core.utils.transformers import BallTransform, SpecialTransform


class StatusFlags(FlagConverter):
    status: discord.Status | None = flag(description="The status you want to set")
    name: str | None = flag(description="Title of the activity, if not custom")
    state: str | None = flag(description="Custom status or subtitle of the activity")
    activity_type: discord.ActivityType | None = flag(
        description="The type of activity", default=discord.ActivityType.custom
    )


class RarityFlags(FlagConverter):
    chunked: bool = flag(default=True, description="Group together countryballs with the same rarity.")
    include_disabled: bool = flag(
        default=False, description="Include the countryballs that are disabled or with a rarity of 0."
    )


class SpawnFlags(FlagConverter):
    countryball: BallTransform | None = flag(
        description="The countryball you want to spawn. Random according to rarities if not specified."
    )
    channel: discord.TextChannel | None = flag(
        description="The channel you want to spawn the countryball in. Current channel if not specified.", default=None
    )
    n: Range[int, 1, 100] = flag(
        description="The number of countryballs to spawn. If no countryball was specified, it's random every time.",
        default=1,
    )
    special: SpecialTransform | None = flag(
        description="Force the countryball to have a special attribute when caught."
    )
    atk_bonus: int | None = flag(description="Force the countryball to have a specific attack bonus when caught.")
    hp_bonus: int | None = flag(description="Force the countryball to have a specific health bonus when caught.")


class GiveBallFlags(FlagConverter):
    countryball: BallTransform = flag(positional=True, description="The countryball you want to give")
    special: SpecialTransform | None = flag(description="A special event to set to this card")
    health_bonus: int | None = flag(description="Force a specific health bonus percentage")
    attack_bonus: int | None = flag(description="Force a specific attack bonus percentage")


class BallsCountFlags(FlagConverter):
    user: discord.User | None = flag(description="The player whose countryballs you are counting")
    countryball: BallTransform | None = flag(description="Restrict countring to a specific countryball")
    special: SpecialTransform | None = flag(description="Restrict counting to a special event")
    deleted: bool = flag(default=False, description="Count the deleted countryballs too")


class TradeHistoryFlags(FlagConverter):
    sort_oldest: bool = flag(description='"yes" to have oldest trades first', default=False)
    days: int | None = flag(description="Retrieve entries from the last n days")


class UserTradeHistoryFlags(TradeHistoryFlags):
    countryball: BallTransform | None = flag(description="The countryball you want to filter the history by")
    user2: discord.User | None = flag(description="The second user you want to check the history of")
    special: SpecialTransform | None = flag(description="The special you want to filter the history by")
