from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("currency_app", "0009_currencysettings_streak_and_dailybonusrole")]

    operations = [
        migrations.AddField(
            model_name="currencysettings",
            name="base_daily_amount",
            field=models.PositiveIntegerField(
                default=1500, help_text="Flat amount claimed by /daily every time, on top of the streak bonus."
            ),
        )
    ]
