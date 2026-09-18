from django.db import migrations


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("bd_models", "0014_alter_ball_options_alter_ballinstance_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="FrameBall",
            fields=[],
            options={
                "verbose_name": "Frame",
                "verbose_name_plural": "Frames",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("bd_models.ball",),
        ),
    ]
