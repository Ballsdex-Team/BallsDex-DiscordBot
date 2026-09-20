from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("collector_app", "0010_elemental_for_every_treasure")]

    operations = [
        migrations.AddField(
            model_name="collectortier",
            name="frame_key",
            field=models.CharField(
                blank=True,
                default="",
                help_text='Frame given to the claimed card, as its key in the Frames section ("09-20-2026", or '
                '"09-20-2026:3" for a frame of one special). Leave empty for a normal card.',
                max_length=32,
            ),
        )
    ]
