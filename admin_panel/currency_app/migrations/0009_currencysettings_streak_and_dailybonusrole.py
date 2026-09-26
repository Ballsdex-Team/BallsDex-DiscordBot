from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("currency_app", "0008_remove_currencysettings_emoji_id_and_more")]

    operations = [
        migrations.AddField(
            model_name="currencysettings",
            name="day1_reward",
            field=models.PositiveIntegerField(default=100, help_text="/daily reward on streak day 1."),
        ),
        migrations.AddField(
            model_name="currencysettings",
            name="day2_reward",
            field=models.PositiveIntegerField(default=200, help_text="/daily reward on streak day 2."),
        ),
        migrations.AddField(
            model_name="currencysettings",
            name="day3_reward",
            field=models.PositiveIntegerField(default=300, help_text="/daily reward on streak day 3."),
        ),
        migrations.AddField(
            model_name="currencysettings",
            name="day4_reward",
            field=models.PositiveIntegerField(default=400, help_text="/daily reward on streak day 4."),
        ),
        migrations.AddField(
            model_name="currencysettings",
            name="day5_reward",
            field=models.PositiveIntegerField(default=500, help_text="/daily reward on streak day 5."),
        ),
        migrations.AddField(
            model_name="currencysettings",
            name="day6_reward",
            field=models.PositiveIntegerField(default=600, help_text="/daily reward on streak day 6."),
        ),
        migrations.AddField(
            model_name="currencysettings",
            name="day7_reward",
            field=models.PositiveIntegerField(default=1000, help_text="/daily reward on streak day 7."),
        ),
        migrations.AddField(
            model_name="currencysettings",
            name="streak_grace_hours",
            field=models.PositiveIntegerField(
                default=48,
                help_text="A player must claim /daily again within this many hours of their last claim to keep "
                "their streak going. Past this window, the streak resets to day 1.",
            ),
        ),
        migrations.CreateModel(
            name="DailyBonusRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "server_id",
                    models.BigIntegerField(help_text="Discord server ID this configuration applies to.", unique=True),
                ),
                ("role_id", models.BigIntegerField(help_text="Role ID granting the flat /daily bonus.")),
                (
                    "bonus_amount",
                    models.PositiveIntegerField(default=500, help_text="Flat bonus added to every /daily claim."),
                ),
            ],
            options={"db_table": "dailybonusrole", "managed": True},
        ),
    ]
