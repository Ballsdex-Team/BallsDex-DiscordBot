from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("eventpass_app", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="quest",
            name="announce",
            field=models.CharField(
                choices=[
                    ("public", "In the channel, where everyone sees it"),
                    ("private", "In the player's DMs only"),
                    ("none", "No message at all"),
                ],
                default="public",
                help_text="Where the message goes when a player completes this quest. Use the DMs for quests that "
                "come back often, so the channel isn't flooded.",
                max_length=8,
                verbose_name="completion message",
            ),
        )
    ]
