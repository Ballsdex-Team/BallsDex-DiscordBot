import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("currency_app", "0010_currencysettings_base_daily_amount")]

    operations = [
        migrations.DeleteModel(name="DailyBonusRole"),
        migrations.CreateModel(
            name="DailyBonusServer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "server_id",
                    models.BigIntegerField(help_text="Discord server ID this configuration applies to.", unique=True),
                ),
            ],
            options={"db_table": "dailybonusserver", "managed": True},
        ),
        migrations.CreateModel(
            name="DailyBonusRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role_id", models.BigIntegerField(help_text="Role ID granting the flat /daily bonus.")),
                (
                    "bonus_amount",
                    models.PositiveIntegerField(default=500, help_text="Flat bonus added to every /daily claim."),
                ),
                (
                    "server",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="roles",
                        to="currency_app.dailybonusserver",
                    ),
                ),
            ],
            options={"db_table": "dailybonusrole", "managed": True, "unique_together": {("server", "role_id")}},
        ),
    ]
