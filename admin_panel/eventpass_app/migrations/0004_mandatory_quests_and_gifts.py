import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("eventpass_app", "0003_quest_announce_ephemeral")]

    operations = [
        migrations.AddField(
            model_name="quest",
            name="mandatory",
            field=models.BooleanField(
                default=False,
                help_text="Needed to finish the tier: its reward, and the tiers asking to finish it, wait for every "
                "mandatory quest. A tier with no mandatory quest needs all its visible quests instead.",
            ),
        ),
        migrations.AlterField(
            model_name="eventpass",
            name="final_reward",
            field=models.ForeignKey(
                blank=True,
                help_text="Given when every tier is finished. Leave empty if the pass has no final reward.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="eventpass_app.reward",
            ),
        ),
        migrations.AlterField(
            model_name="passtier",
            name="reward",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional reward for finishing the tier: every mandatory quest completed, or every visible "
                "quest when none is mandatory.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="eventpass_app.reward",
            ),
        ),
        migrations.AlterField(
            model_name="quest",
            name="max_rarity",
            field=models.FloatField(
                blank=True, help_text="Highest rarity value counted: 60 keeps T60 and everything rarer.", null=True
            ),
        ),
        migrations.AlterField(
            model_name="quest",
            name="min_rarity",
            field=models.FloatField(
                blank=True,
                help_text="Lowest rarity value counted. A lower value is rarer: 50 leaves out everything rarer "
                "than T50.",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="quest",
            name="type",
            field=models.CharField(
                choices=[
                    ("catch", "Catch treasures"),
                    ("obtain", "Obtain treasures (catch, trade, pack, craft...)"),
                    ("command", "Use a command"),
                    ("trade", "Complete trades"),
                    ("trade_treasures", "Exchange treasures in trades"),
                    ("give_treasures", "Give treasures to players"),
                    ("friend", "Add friends"),
                    ("battle_win", "Win battles"),
                    ("give_currency", "Give berries to players"),
                    ("receive_currency", "Receive berries from players"),
                    ("catch_currency", "Earn berries by catching treasures"),
                    ("spend_currency", "Spend berries"),
                    ("craft", "Craft (claim a collector card)"),
                    ("pack_buy", "Buy packs"),
                    ("merchant_buy", "Buy from the merchant"),
                    ("shop_buy", "Buy from Buggy's shop"),
                    ("sell", "Sell treasures to Buggy"),
                    ("auction_create", "List treasures on the auction house"),
                    ("auction_bid", "Place bids on the auction house"),
                    ("auction_won", "Win auctions"),
                ],
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="tierrequirement",
            name="kind",
            field=models.CharField(
                choices=[
                    ("finish_previous", "Finish the previous tier (its mandatory quests)"),
                    ("quests_all", "Complete these quests"),
                    ("quests_count", "Complete a number of quests of the pass"),
                    ("previous_tier", "Unlock the previous tier"),
                    ("own_treasures", "Own treasures (tokens, a special...)"),
                    ("currency", "Have berries"),
                    ("date", "Wait until a date"),
                ],
                max_length=16,
            ),
        ),
    ]
