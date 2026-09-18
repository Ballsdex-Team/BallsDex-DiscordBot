from django.db import migrations

ELEMENTS = ("Air", "Fire", "Water", "Earth")


def create_elemental_tier(apps, schema_editor):
    """
    Add an "Elemental" tier to every collector: every treasure of its Tier 1 recipe is needed in the four elements,
    and they are used up when claiming. The card given has the Elemental special.

    Collectors created later need the "Add a tier" admin action.
    """
    Special = apps.get_model("bd_models", "Special")
    CollectorTierLevel = apps.get_model("collector_app", "CollectorTierLevel")
    CollectorTier = apps.get_model("collector_app", "CollectorTier")
    CollectorRequirement = apps.get_model("collector_app", "CollectorRequirement")

    elemental = Special.objects.filter(name__iexact="Elemental").first()
    elements = [Special.objects.filter(name__iexact=name).first() for name in ELEMENTS]
    tier_1 = CollectorTierLevel.objects.filter(name="Tier 1").first()
    if elemental is None or tier_1 is None or not all(elements):
        # another instance of the bot without these specials, nothing to set up
        return

    # the tier may already have been created by hand, it is then reused as is
    level, _ = CollectorTierLevel.objects.get_or_create(
        name="Elemental",
        defaults={
            "position": 3,
            "special": elemental,
            "claimable": True,
            # the treasures are used up when claiming, there is nothing left to watch afterwards
            "monitored": False,
        },
    )

    recipes: dict[int, list[int]] = {}
    for collector_id, ball_id in (
        CollectorRequirement.objects.filter(level=tier_1, ball__isnull=False)
        .order_by("pk")
        .values_list("collector_id", "ball_id")
    ):
        balls = recipes.setdefault(collector_id, [])
        if ball_id not in balls:
            balls.append(ball_id)

    already_set_up = set(CollectorTier.objects.filter(level=level).values_list("collector_id", flat=True))
    tradeable_by_collector = dict(CollectorTier.objects.filter(level=tier_1).values_list("collector_id", "tradeable"))

    tiers, requirements = [], []
    for collector_id, ball_ids in recipes.items():
        if collector_id in already_set_up:
            continue
        tiers.append(
            CollectorTier(
                collector_id=collector_id, level=level, tradeable=tradeable_by_collector.get(collector_id, True)
            )
        )
        requirements.extend(
            CollectorRequirement(
                collector_id=collector_id, level=level, ball_id=ball_id, special=element, amount=1, delete_balls=True
            )
            for ball_id in ball_ids
            for element in elements
        )
    CollectorTier.objects.bulk_create(tiers, batch_size=500)
    CollectorRequirement.objects.bulk_create(requirements, batch_size=1000)


def remove_elemental_tier(apps, schema_editor):
    CollectorTierLevel = apps.get_model("collector_app", "CollectorTierLevel")
    CollectorTier = apps.get_model("collector_app", "CollectorTier")
    CollectorRequirement = apps.get_model("collector_app", "CollectorRequirement")

    level = CollectorTierLevel.objects.filter(name="Elemental").first()
    if level is None:
        return
    CollectorRequirement.objects.filter(level=level).delete()
    CollectorTier.objects.filter(level=level).delete()
    # kept if players already claimed cards of this tier, the level is protected by their instances
    if not level.instances.exists():
        level.delete()


class Migration(migrations.Migration):
    dependencies = [("collector_app", "0007_collector_tiers_cleanup"), ("bd_models", "0020_playerdatadeletion")]

    operations = [migrations.RunPython(create_elemental_tier, remove_elemental_tier)]
