from typing import TYPE_CHECKING

import discord
from auction_house_app import services
from discord import app_commands
from discord.ext import commands

from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.transformers import BallInstanceTransform
from settings.models import settings
from settings.utils import format_currency

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

# every embed uses the color configured in the admin panel settings
TREASURES_COLOR = settings.embed_colour


class TreasureSale(commands.Cog):
    """
    Sell treasures directly to Buggy's Auction House.

    Standalone top-level `/sell` rather than a `/treasures` group: this bot's core `/balls`
    group is itself renamed to "treasures" (matching the collectible name), so a second
    "treasures" command group would collide with it.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command(name="sell")
    async def sell(self, interaction: discord.Interaction["BallsDexBot"], countryball: BallInstanceTransform):
        """
        Sell a treasure directly to Buggy's Auction House for an instant payout.

        Parameters
        ----------
        countryball: BallInstance
            The treasure you want to sell.
        """
        if not countryball:
            return
        await interaction.response.defer(thinking=True, ephemeral=True)

        if not countryball.is_tradeable or countryball.deleted:
            await interaction.followup.send(f"This {settings.collectible_name} can't be sold.")
            return
        if countryball.special_id is not None:
            await interaction.followup.send(
                "Special treasures can't be sold directly to Buggy — list them for auction instead with "
                "`/auction create`."
            )
            return

        auction_settings, _, stat_modifiers = await services.load_pricing_context()
        if countryball.countryball.rarity == auction_settings.excluded_rarity:
            await interaction.followup.send("This treasure's rarity can't be sold to Buggy.")
            return
        if await services.is_excluded_ball(countryball.ball_id, auction_settings):
            await interaction.followup.send("This treasure can't be sold to Buggy.")
            return
        if await services.is_already_committed(countryball):
            await interaction.followup.send("This treasure is already listed or already belongs to Buggy.")
            return

        sale_count = await services.direct_sale_count_today(countryball.player_id)
        if sale_count >= auction_settings.direct_sale_daily_limit:
            reset_at = services.next_daily_sale_reset()
            await interaction.followup.send(
                f"You've reached the daily limit of {auction_settings.direct_sale_daily_limit} direct sales "
                f"to Buggy (across every server). Try again {discord.utils.format_dt(reset_at, 'R')}."
            )
            return

        server_id = interaction.guild_id
        assert server_id is not None
        bonus_percent = await services.get_total_booster_bonus(interaction.user, server_id, "sell_bonus_percent")
        price = services.direct_sale_price_for(countryball, auction_settings, stat_modifiers, bonus_percent)

        embed = discord.Embed(
            title="Sell to Buggy's Auction House",
            description=(
                f"{countryball.description(include_emoji=True, bot=self.bot)}\n\n"
                f"Buggy offers you **{format_currency(price, False, self.bot)}** for this "
                f"{settings.collectible_name}{' (booster bonus included)' if bonus_percent else ''}.\n\n"
                "This is final — the treasure leaves your inventory immediately."
            ),
            color=TREASURES_COLOR,
        )
        view = ConfirmChoiceView(interaction, accept_message="Sold!", cancel_message="Sale cancelled.")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        await view.wait()
        if not view.value:
            return

        resale_price = max(price, round(price * (1 + auction_settings.resale_markup_percent / 100)))
        try:
            await services.safe_settle(
                services.settle_direct_sale, countryball.pk, price, resale_price, server_id, countryball.player_id
            )
        except RuntimeError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        await interaction.followup.send(f"Sold for **{format_currency(price, False, self.bot)}**!", ephemeral=True)
