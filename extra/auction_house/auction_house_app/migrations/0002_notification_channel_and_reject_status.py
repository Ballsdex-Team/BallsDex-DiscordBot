from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("auction_house_app", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="auctionguildconfig",
            name="notification_channel_id",
            field=models.BigIntegerField(
                blank=True, null=True, help_text="Channel where sale notifications (accepted offers) are posted."
            ),
        ),
        migrations.AlterField(
            model_name="auctionoffer",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("accepted", "Accepted"),
                    ("cancelled", "Cancelled"),
                    ("rejected", "Rejected"),
                    ("refunded", "Refunded"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
