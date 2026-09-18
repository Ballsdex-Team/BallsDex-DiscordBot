from django.db import migrations


def move_collectors_to_tier_1(apps, schema_editor):
    """
    Every existing collector becomes the "Tier 1" of itself, keeping its special and tradeability. A disabled
    "Tier 2" is created, ready to be configured. Collector cards claimed before this migration are not monitored.
    """
    Special = apps.get_model("bd_models", "Special")
    Collector = apps.get_model("collector_app", "Collector")
    CollectorTierLevel = apps.get_model("collector_app", "CollectorTierLevel")
    CollectorTier = apps.get_model("collector_app", "CollectorTier")
    CollectorRequirement = apps.get_model("collector_app", "CollectorRequirement")
    CollectorInstance = apps.get_model("collector_app", "CollectorInstance")

    collector_special = Special.objects.filter(name__iexact="Collector").first()
    gold_special = Special.objects.filter(name__iexact="Gold Collector Card").first()

    tier_1 = CollectorTierLevel.objects.create(name="Tier 1", position=1, special=collector_special)
    CollectorTierLevel.objects.create(name="Tier 2", position=2, special=gold_special, claimable=False)

    tiers = []
    for collector in Collector.objects.all():
        uses_tier_special = collector_special is not None and collector.special_id == collector_special.pk
        tiers.append(
            CollectorTier(
                collector=collector,
                level=tier_1,
                special_id=None if uses_tier_special else collector.special_id,
                no_special=collector.special_id is None,
                tradeable=collector.tradeable,
            )
        )
    CollectorTier.objects.bulk_create(tiers, batch_size=500)

    CollectorRequirement.objects.update(level=tier_1)
    CollectorInstance.objects.update(level=tier_1, monitored=False)


class Migration(migrations.Migration):
    dependencies = [("bd_models", "0020_playerdatadeletion"), ("collector_app", "0005_collector_tiers")]

    operations = [migrations.RunPython(move_collectors_to_tier_1, migrations.RunPython.noop)]
