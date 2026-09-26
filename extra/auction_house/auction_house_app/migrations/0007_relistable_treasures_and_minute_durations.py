import django.db.models.deletion
from django.db import migrations, models
from django.db.models import F, Q


def hours_to_minutes(apps, schema_editor):
    """Existing values were expressed in hours; the columns now hold minutes."""
    AuctionSettings = apps.get_model("auction_house_app", "AuctionSettings")
    AuctionSettings.objects.update(
        min_listing_minutes=F("min_listing_minutes") * 60, max_listing_minutes=F("max_listing_minutes") * 60
    )
    AuctionListing = apps.get_model("auction_house_app", "AuctionListing")
    AuctionListing.objects.update(duration_minutes=F("duration_minutes") * 60)


def minutes_to_hours(apps, schema_editor):
    AuctionSettings = apps.get_model("auction_house_app", "AuctionSettings")
    AuctionSettings.objects.update(
        min_listing_minutes=F("min_listing_minutes") / 60, max_listing_minutes=F("max_listing_minutes") / 60
    )
    AuctionListing = apps.get_model("auction_house_app", "AuctionListing")
    AuctionListing.objects.update(duration_minutes=F("duration_minutes") / 60)


class Migration(migrations.Migration):
    dependencies = [("auction_house_app", "0006_directsalerecord_details")]

    operations = [
        # -- listing durations move from hours to minutes ------------------------------------
        # The check constraint references both columns, so it has to go before the rename and
        # come back afterwards. Multiplying both sides by 60 preserves min <= max throughout.
        migrations.RemoveConstraint(model_name="auctionsettings", name="auctionsettings_listing_hours_min_lte_max"),
        migrations.RenameField(
            model_name="auctionsettings", old_name="min_listing_hours", new_name="min_listing_minutes"
        ),
        migrations.RenameField(
            model_name="auctionsettings", old_name="max_listing_hours", new_name="max_listing_minutes"
        ),
        migrations.RenameField(model_name="auctionlisting", old_name="duration_hours", new_name="duration_minutes"),
        migrations.RunPython(hours_to_minutes, minutes_to_hours),
        migrations.AlterField(
            model_name="auctionsettings",
            name="min_listing_minutes",
            field=models.PositiveIntegerField(
                default=60,
                help_text="Minimum duration a player can choose when listing a card for auction, in minutes.",
            ),
        ),
        migrations.AlterField(
            model_name="auctionsettings",
            name="max_listing_minutes",
            field=models.PositiveIntegerField(
                default=4320,
                help_text="Maximum duration a player can choose when listing a card for auction, in minutes.",
            ),
        ),
        migrations.AddConstraint(
            model_name="auctionsettings",
            constraint=models.CheckConstraint(
                condition=Q(min_listing_minutes__lte=F("max_listing_minutes")),
                name="auctionsettings_listing_minutes_min_lte_max",
            ),
        ),
        # -- giveaways can be pinned to a single server --------------------------------------
        migrations.AddField(
            model_name="auctionsettings",
            name="giveaway_server_id",
            field=models.BigIntegerField(
                null=True,
                blank=True,
                help_text="Restrict giveaways to this server: only players active here can win, and the "
                "announcement is posted here. Leave empty to draw from players across every server the bot "
                "is in.",
            ),
        ),
        # -- a treasure may be committed again once its previous record is closed ------------
        # These were OneToOne fields, so a treasure could only ever have ONE listing / stock /
        # featured item row in its entire lifetime — relisting an unsold treasure, or selling
        # back one bought from Buggy, failed on the unique constraint. Existing rows are kept as
        # history, and uniqueness is narrowed to the live state only.
        migrations.AlterField(
            model_name="auctionlisting",
            name="instance",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="auction_listings",
                to="bd_models.ballinstance",
            ),
        ),
        migrations.AlterField(
            model_name="hotelstock",
            name="instance",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name="hotel_stocks", to="bd_models.ballinstance"
            ),
        ),
        migrations.AlterField(
            model_name="featuredauctionitem",
            name="instance",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="featured_auction_items",
                to="bd_models.ballinstance",
            ),
        ),
        migrations.AddConstraint(
            model_name="auctionlisting",
            constraint=models.UniqueConstraint(
                fields=("instance",), condition=Q(status="active"), name="auctionlisting_one_active_per_instance"
            ),
        ),
        migrations.AddConstraint(
            model_name="hotelstock",
            constraint=models.UniqueConstraint(
                fields=("instance",),
                condition=Q(status="available"),
                name="auctionhotelstock_one_available_per_instance",
            ),
        ),
    ]
