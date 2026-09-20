from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("eventpass_app", "0002_quest_announce")]

    operations = [
        migrations.AlterField(
            model_name="quest",
            name="announce",
            field=models.CharField(
                choices=[
                    ("public", "In the channel, where everyone sees it"),
                    ("ephemeral", "In the channel, but only the player sees it"),
                    ("private", "In the player's DMs only"),
                    ("none", "No message at all"),
                ],
                default="public",
                help_text="Where the message goes when a player completes this quest. The private one in the "
                "channel needs the player to have used the bot in the last 15 minutes, otherwise it lands in their "
                "DMs.",
                max_length=9,
                verbose_name="completion message",
            ),
        )
    ]
