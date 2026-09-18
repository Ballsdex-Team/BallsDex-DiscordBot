from django.db import migrations
from django.db.models import Count, Q

ELEMENTS = ("Air", "Fire", "Water", "Earth")


def obtainable_treasures(Ball, ItemBall):
    """
    Every treasure players can get: the ones spawning, and the ones only found in packs.
    """
    return Ball.objects.filter(Q(enabled=True) | Q(pk__in=ItemBall.objects.values("ball_id")))


def add_elemental_collectors(apps, schema_editor):
    """
    Give an Elemental recipe to every treasure players can get which doesn't have a collector yet, pack treasures
    included: the treasure in the four elements, used up when claiming, for its Elemental card. These collectors
    only have the Elemental tier, no Tier 1 or Tier 2.
    """
    Ball = apps.get_model("bd_models", "Ball")
    Special = apps.get_model("bd_models", "Special")
    ItemBall = apps.get_model("currency_app", "ItemBall")
    Collector = apps.get_model("collector_app", "Collector")
    CollectorTierLevel = apps.get_model("collector_app", "CollectorTierLevel")
    CollectorTier = apps.get_model("collector_app", "CollectorTier")
    CollectorRequirement = apps.get_model("collector_app", "CollectorRequirement")

    level = CollectorTierLevel.objects.filter(name="Elemental").first()
    elements = [Special.objects.filter(name__iexact=name).first() for name in ELEMENTS]
    if level is None or not all(elements):
        # another instance of the bot without these specials, nothing to set up
        return

    treasures = (
        obtainable_treasures(Ball, ItemBall)
        .exclude(pk__in=Collector.objects.filter(ball__isnull=False).values("ball_id"))
        .order_by("country")
    )
    taken = set(Collector.objects.values_list("name", flat=True))
    collectors = []
    for ball in treasures:
        # named after the treasure like most collectors, the name must be unique
        name = next((x for x in (ball.country, f"{ball.country} (Elemental)"[:64]) if x not in taken), None)
        if name is None:
            continue
        taken.add(name)
        collectors.append(Collector(name=name, ball=ball))
    Collector.objects.bulk_create(collectors, batch_size=500)

    CollectorTier.objects.bulk_create(
        # not tradeable, like most collector cards
        (CollectorTier(collector=collector, level=level, tradeable=False) for collector in collectors),
        batch_size=500,
    )
    CollectorRequirement.objects.bulk_create(
        (
            CollectorRequirement(
                collector=collector,
                level=level,
                ball_id=collector.ball_id,
                special=element,
                amount=1,
                delete_balls=True,
            )
            for collector in collectors
            for element in elements
        ),
        batch_size=1000,
    )


def remove_elemental_collectors(apps, schema_editor):
    """
    Delete the collectors made by this migration: an Elemental tier alone, asking for their own treasure in the four
    elements. The ones players already claimed are kept.
    """
    Special = apps.get_model("bd_models", "Special")
    Collector = apps.get_model("collector_app", "Collector")
    CollectorTierLevel = apps.get_model("collector_app", "CollectorTierLevel")
    CollectorRequirement = apps.get_model("collector_app", "CollectorRequirement")
    CollectorInstance = apps.get_model("collector_app", "CollectorInstance")

    level = CollectorTierLevel.objects.filter(name="Elemental").first()
    element_ids = {x.pk for x in (Special.objects.filter(name__iexact=name).first() for name in ELEMENTS) if x}
    if level is None:
        return

    claimed = set(CollectorInstance.objects.values_list("collector_id", flat=True))
    candidates = (
        Collector.objects.annotate(tier_count=Count("tiers", distinct=True))
        .filter(tier_count=1, tiers__level=level)
        .exclude(pk__in=claimed)
    )
    made = []
    for collector in candidates:
        requirements = list(CollectorRequirement.objects.filter(collector=collector))
        if (
            len(requirements) == len(ELEMENTS)
            and {requirement.special_id for requirement in requirements} == element_ids
            and all(x.ball_id == collector.ball_id and x.amount == 1 and x.delete_balls for x in requirements)
        ):
            made.append(collector.pk)
    Collector.objects.filter(pk__in=made).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("collector_app", "0009_craft_and_tier_2"),
        ("bd_models", "0020_playerdatadeletion"),
        ("currency_app", "0014_berrytransaction_collector_claim"),
    ]

    operations = [migrations.RunPython(add_elemental_collectors, remove_elemental_collectors)]
