from django.db import migrations

TIER_2_SPECIAL = "Boss"
TIER_2_PREVIOUS_SPECIAL = "Gold Collector Card"


def recipes_of(CollectorRequirement, level) -> dict[int, list]:
    recipes: dict[int, list] = {}
    for requirement in CollectorRequirement.objects.filter(level=level).order_by("pk"):
        recipes.setdefault(requirement.collector_id, []).append(requirement)
    return recipes


def is_single_treasure(requirements: list) -> bool:
    """
    Whether the recipe only asks for copies of one treasure, like "30 Luffy".
    """
    return len(requirements) == 1 and requirements[0].ball_id is not None and requirements[0].special_id is None


def split_crafts_and_add_tier_2(apps, schema_editor):
    """
    Collectors asking for copies of a single treasure keep their "Tier 1" and get a "Tier 2" asking for twice as
    many, which gives a Boss card for now. Collectors mixing several treasures move to a "Craft" tier, along with
    the cards already claimed. Tier 2 stays disabled until its "claimable" box is ticked in the admin panel.

    Collectors created later get their Tier 2 with the "Add a tier" admin action (multiplier 2).
    """
    Special = apps.get_model("bd_models", "Special")
    CollectorTierLevel = apps.get_model("collector_app", "CollectorTierLevel")
    CollectorTier = apps.get_model("collector_app", "CollectorTier")
    CollectorRequirement = apps.get_model("collector_app", "CollectorRequirement")
    CollectorInstance = apps.get_model("collector_app", "CollectorInstance")

    tier_1 = CollectorTierLevel.objects.filter(name="Tier 1").first()
    tier_2 = CollectorTierLevel.objects.filter(name="Tier 2").first()
    if tier_1 is None or tier_2 is None:
        return

    recipes = recipes_of(CollectorRequirement, tier_1)
    single = {collector_id: reqs[0] for collector_id, reqs in recipes.items() if is_single_treasure(reqs)}
    crafts = [collector_id for collector_id in recipes if collector_id not in single]

    # the recipes mixing several treasures become crafts, giving the same card as before
    craft, _ = CollectorTierLevel.objects.get_or_create(
        name="Craft",
        defaults={
            "position": tier_1.position,
            "emoji": tier_1.emoji,
            "special_id": tier_1.special_id,
            "claimable": True,
            "monitored": tier_1.monitored,
        },
    )
    for model in (CollectorTier, CollectorRequirement, CollectorInstance):
        model.objects.filter(level=tier_1, collector_id__in=crafts).update(level=craft)

    boss = Special.objects.filter(name__iexact=TIER_2_SPECIAL).first()
    if boss is not None:
        tier_2.special = boss
        tier_2.save(update_fields=("special",))

    # a collector which already has a Tier 2 keeps it as it is
    already_set_up = set(CollectorTier.objects.filter(level=tier_2).values_list("collector_id", flat=True))
    tier_1_tiers = {tier.collector_id: tier for tier in CollectorTier.objects.filter(level=tier_1)}
    tiers, requirements = [], []
    for collector_id, requirement in single.items():
        base = tier_1_tiers.get(collector_id)
        if collector_id in already_set_up or base is None:
            continue
        tiers.append(
            CollectorTier(
                collector_id=collector_id,
                level=tier_2,
                enabled=base.enabled,
                tradeable=base.tradeable,
                price=base.price,
            )
        )
        requirements.append(
            CollectorRequirement(
                collector_id=collector_id,
                level=tier_2,
                ball_id=requirement.ball_id,
                amount=requirement.amount * 2,
                delete_balls=requirement.delete_balls,
            )
        )
    CollectorTier.objects.bulk_create(tiers, batch_size=500)
    CollectorRequirement.objects.bulk_create(requirements, batch_size=500)


def merge_crafts_back(apps, schema_editor):
    Special = apps.get_model("bd_models", "Special")
    CollectorTierLevel = apps.get_model("collector_app", "CollectorTierLevel")
    CollectorTier = apps.get_model("collector_app", "CollectorTier")
    CollectorRequirement = apps.get_model("collector_app", "CollectorRequirement")
    CollectorInstance = apps.get_model("collector_app", "CollectorInstance")

    tier_1 = CollectorTierLevel.objects.filter(name="Tier 1").first()
    tier_2 = CollectorTierLevel.objects.filter(name="Tier 2").first()
    craft = CollectorTierLevel.objects.filter(name="Craft").first()
    if tier_1 is None or tier_2 is None:
        return

    if craft is not None:
        for model in (CollectorTier, CollectorRequirement, CollectorInstance):
            model.objects.filter(level=craft).update(level=tier_1)
        craft.delete()

    # only the Tier 2 recipes this migration made: twice the only treasure of Tier 1
    doubled = {
        (collector_id, reqs[0].ball_id, reqs[0].amount * 2)
        for collector_id, reqs in recipes_of(CollectorRequirement, tier_1).items()
        if is_single_treasure(reqs)
    }
    tier_2_recipes = recipes_of(CollectorRequirement, tier_2)
    made = [
        collector_id
        for collector_id, reqs in tier_2_recipes.items()
        if is_single_treasure(reqs) and (collector_id, reqs[0].ball_id, reqs[0].amount) in doubled
    ]
    CollectorRequirement.objects.filter(level=tier_2, collector_id__in=made).delete()
    CollectorTier.objects.filter(level=tier_2, collector_id__in=made).delete()

    previous = Special.objects.filter(name__iexact=TIER_2_PREVIOUS_SPECIAL).first()
    if previous is not None and tier_2.special is not None and tier_2.special.name.lower() == TIER_2_SPECIAL.lower():
        tier_2.special = previous
        tier_2.save(update_fields=("special",))


class Migration(migrations.Migration):
    dependencies = [("collector_app", "0008_elemental_tier"), ("bd_models", "0020_playerdatadeletion")]

    operations = [migrations.RunPython(split_crafts_and_add_tier_2, merge_crafts_back)]
