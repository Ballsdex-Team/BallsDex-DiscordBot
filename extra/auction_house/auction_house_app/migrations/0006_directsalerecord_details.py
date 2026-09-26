from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("auction_house_app", "0005_featured_auctions_and_more")]

    operations = [
        migrations.AddField(
            model_name="directsalerecord",
            name="instance_id",
            field=models.PositiveBigIntegerField(
                default=0, help_text="ID of the treasure instance sold, for reference even after it moves on."
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="directsalerecord",
            name="special_name",
            field=models.CharField(
                blank=True, max_length=64, null=True, help_text="Special the treasure had, if any (snapshot)."
            ),
        ),
        migrations.AddField(
            model_name="directsalerecord",
            name="attack_bonus",
            field=models.IntegerField(default=0, help_text="Attack stat bonus at the time of sale (snapshot)."),
        ),
        migrations.AddField(
            model_name="directsalerecord",
            name="health_bonus",
            field=models.IntegerField(default=0, help_text="Health stat bonus at the time of sale (snapshot)."),
        ),
    ]
