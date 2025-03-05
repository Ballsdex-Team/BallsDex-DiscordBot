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
    chunked: bool = flag(
        default=True, description="Group together countryballs with the same rarity."
    )
    include_disabled: bool = flag(
        default=False,
        description="Include the countryballs that are disabled or with a rarity of 0.",
    )


class SpawnFlags(FlagConverter):
    countryball: BallTransform | None = flag(
        description="The countryball you want to spawn. Random according to rarities "
        "if not specified."
    )
    channel: discord.TextChannel | None = flag(
        description="The channel you want to spawn the countryball in. Current channel "
        "if not specified.",
        default=None,
    )
    n: Range[int, 1, 100] = flag(
        description="The number of countryballs to spawn. If no countryball was specified, "
        "it's random every time.",
        default=1,
    )
    special: SpecialTransform | None = flag(
        description="Force the countryball to have a special attribute when caught."
    )
    atk_bonus: int | None = flag(
        description="Force the countryball to have a specific attack bonus when caught."
    )
    hp_bonus: int | None = flag(
        description="Force the countryball to have a specific health bonus when caught."
    )


class GiveBallFlags(FlagConverter):
    countryball: BallTransform = flag(positional=True)
    special: SpecialTransform | None = None
    health_bonus: int | None = None
    attack_bonus: int | None = None


class BallsCountFlags(FlagConverter):
    user: discord.User | None = None
    countryball: BallTransform | None = None
    special: SpecialTransform | None = None
