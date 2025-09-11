import enum
from typing import TYPE_CHECKING

from tortoise.expressions import F, RawSQL

if TYPE_CHECKING:
    from tortoise.queryset import QuerySet

    from ballsdex.core.models import BallInstance


class FilteringChoices(enum.Enum):
    only_specials = "special"
    non_specials = "non_special"
    self_caught = "self_caught"
    this_server = "this_server"


class SortingChoices(enum.Enum):
    alphabetic = "ball__country"
    catch_date = "-catch_date"
    rarity = "ball__rarity"
    special = "special__id"
    health = "health"
    attack = "attack"
    health_bonus = "-health_bonus"
    attack_bonus = "-attack_bonus"
    stats_bonus = "stats"
    # total_stats = "total_stats"
    duplicates = "duplicates"


def sort_balls(
    sort: SortingChoices, queryset: "QuerySet[BallInstance]"
) -> "QuerySet[BallInstance]":
    """
    Edit a queryset in place to apply the selected sorting options. You can call this function
    multiple times with the same queryset to have multiple sort methods.

    Parameters
    ----------
    sort: SortingChoices
        One of the supported sorting methods
    queryset: QuerySet[BallInstance]
        An existing queryset of ball instances. This can be obtained with, for example,
        ``BallInstance.all()`` or ``BallInstance.filter(player=x)``
        **without awaiting the result!**

    Returns
    -------
    QuerySet[BallInstance]
        The same queryset modified to apply the ordering. Await it to obtain the result.
    """
    if sort == SortingChoices.duplicates:
        return queryset.annotate(count=RawSQL("COUNT(*) OVER (PARTITION BY ball_id)")).order_by(
            "-count"
        )
    elif sort == SortingChoices.stats_bonus:
        return queryset.annotate(stats_bonus=F("health_bonus") + F("attack_bonus")).order_by(
            "-stats_bonus"
        )
    elif sort == SortingChoices.health or sort == SortingChoices.attack:
        # Use the sorting name as the annotation key to avoid issues when this function
        # is called multiple times. Using the same annotation name twice will error.
        return queryset.annotate(
            **{f"{sort.value}_sort": F(f"{sort.value}_bonus") + F(f"ball__{sort.value}")}
        ).order_by(f"-{sort.value}_sort")
    # elif sort == SortingChoices.total_stats:
    #     return (
    #         queryset.select_related("ball")
    #         .annotate(
    #             stats=RawSQL("ballinstance__ball.health + ballinstance__ball.attack :: BIGINT")
    #         )
    #         .order_by("-stats")
    #     )
    elif sort == SortingChoices.rarity:
        return queryset.order_by(sort.value, "ball__country")
    else:
        return queryset.order_by(sort.value)


def filter_balls(
    filter: FilteringChoices, queryset: "QuerySet[BallInstance]", guild_id: int | None = None
) -> "QuerySet[BallInstance]":
    """
    Edit a list of ball instances in place to apply the selected filtering options.

    Parameters
    ----------
    filter: FilteringChoices
        One of the supported filtering methods
    balls: QuerySet[BallInstance]
        A ballinstance queryset.
    guild_id: int | None
        The ID of the server to filter by. Only used for the ``this_server`` filter.
        If not provided, this filter will be ignored.

    Returns
    -------
    QuerySet[BallInstance]
        The modified query applying the filtering.
    """
    if filter == FilteringChoices.only_specials:
        return queryset.exclude(special=None)
    elif filter == FilteringChoices.non_specials:
        return queryset.filter(special=None)
    elif filter == FilteringChoices.self_caught:
        return queryset.filter(trade_player=None)
    elif filter == FilteringChoices.this_server and guild_id is not None:
        return queryset.filter(server_id=guild_id)
    else:
        return queryset
