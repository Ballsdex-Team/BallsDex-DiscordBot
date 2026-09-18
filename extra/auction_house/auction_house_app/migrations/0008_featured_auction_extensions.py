from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("auction_house_app", "0007_relistable_treasures_and_minute_durations")]

    operations = [
        migrations.AddField(
            model_name="auctionsettings",
            name="featured_extension_window_minutes",
            field=models.PositiveIntegerField(
                default=10,
                help_text="A bid placed on a featured auction when less than this many minutes remain extends the "
                "auction. Set to 0 to disable extensions.",
            ),
        ),
        migrations.AddField(
            model_name="auctionsettings",
            name="featured_extension_minutes",
            field=models.PositiveIntegerField(
                default=10,
                help_text="How many minutes are added to a featured auction when a last-minute bid comes in. There "
                "is no limit, every last-minute bid extends it again.",
            ),
        ),
    ]
