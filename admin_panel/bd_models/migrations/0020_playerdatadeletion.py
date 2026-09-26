from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bd_models", "0019_guildconfig_tips_enabled")]

    operations = [
        migrations.CreateModel(
            name="PlayerDataDeletion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "discord_id",
                    models.BigIntegerField(help_text="Discord user ID of the account that deleted its data"),
                ),
                ("deleted_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "playerdatadeletion",
                "managed": True,
                "indexes": [models.Index(fields=["discord_id", "-deleted_at"], name="playerdatadel_discord_idx")],
            },
        )
    ]
