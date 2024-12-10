import enum
from typing import TYPE_CHECKING

from tortoise.expressions import F, RawSQL

if TYPE_CHECKING:
    from tortoise.queryset import QuerySet

    from ballsdex.core.models import BallInstance


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
    total_stats = "total_stats"
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
            **{sort.value: F(f"{sort.value}_bonus") + F(f"ball__{sort.value}")}
        ).order_by(f"-{sort.value}")
    elif sort == SortingChoices.total_stats:
        return queryset.annotate(
            stats=F("health_bonus") + F("ball__health") + F("attack_bonus") + F("ball__attack")
        ).order_by("-stats")
    elif sort == SortingChoices.rarity:
        return queryset.order_by(sort.value, "ball__country")
    else:
        return queryset.order_by(sort.value)
