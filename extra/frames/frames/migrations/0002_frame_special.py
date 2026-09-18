from django.db import migrations

FRAME_SPECIAL = "Frame"


def create_frame_special(apps, schema_editor):
    """
    A "Frame" special for the special option of the commands: picking it selects the framed treasures. It is never
    given to treasures, its rarity is 0.
    """
    Special = apps.get_model("bd_models", "Special")
    if not Special.objects.filter(name__iexact=FRAME_SPECIAL).exists():
        Special.objects.create(
            name=FRAME_SPECIAL,
            emoji="\N{FRAME WITH PICTURE}\N{VARIATION SELECTOR-16}",
            rarity=0,
            hidden=False,
            tradeable=True,
        )


def remove_frame_special(apps, schema_editor):
    Special = apps.get_model("bd_models", "Special")
    BallInstance = apps.get_model("bd_models", "BallInstance")
    for special in Special.objects.filter(name__iexact=FRAME_SPECIAL):
        if not BallInstance.objects.filter(special=special).exists():
            special.delete()


class Migration(migrations.Migration):
    dependencies = [("frames", "0001_initial"), ("bd_models", "0020_playerdatadeletion")]

    operations = [migrations.RunPython(create_frame_special, remove_frame_special)]
