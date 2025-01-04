from __future__ import annotations

from typing import TYPE_CHECKING, List

import discord

from ballsdex.core.models import BallInstance
from ballsdex.core.utils import menus
from ballsdex.core.utils.paginator import Pages

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class CountryballsSource(menus.ListPageSource):
    """
    A data source for paginating a list of BallInstance objects.

    This class provides logic for formatting and managing a paginated view
    of countryballs for display in Discord embeds.
    """
    def __init__(self, entries: List[BallInstance]):
        super().__init__(entries, per_page=25)

    async def format_page(self, menu: CountryballsSelector, balls: List[BallInstance]):
        menu.set_options(balls)
        return True  # signal to edit the page


class CountryballsSelector(Pages):
    """
    A pagination menu for displaying and selecting countryballs.

    This class uses the `Pages` paginator and integrates a dropdown menu
    for users to select a countryball.
    """

    def __init__(self, interaction: discord.Interaction["BallsDexBot"], balls: List[BallInstance]):
        self.bot = interaction.client
        source = CountryballsSource(balls)
        super().__init__(source, interaction=interaction)
        self.add_item(self.select_ball_menu)

    def set_options(self, balls: List[BallInstance]):
        """
        Formats a page of countryballs and signals the selector to update.
        """
        options: List[discord.SelectOption] = []
        for ball in balls:
            emoji = self.bot.get_emoji(int(ball.countryball.emoji_id))
            favorite = "❤️ " if ball.favorite else ""
            special = ball.special_emoji(self.bot, True)
            options.append(
                discord.SelectOption(
                    label=f"{favorite}{special}#{ball.pk:0X} {ball.countryball.country}",
                    description=(
                        f"ATK: {ball.attack}({ball.attack_bonus:+d}%) "
                        f"• HP: {ball.health}({ball.health_bonus:+d}%) • "
                        f"{ball.catch_date.strftime('%Y/%m/%d | %H:%M')}"
                    ),
                    emoji=emoji,
                    value=f"{ball.pk}",
                )
            )
        self.select_ball_menu.options = options

    @discord.ui.select()
    async def select_ball_menu(self, interaction: discord.Interaction, item: discord.ui.Select):
        """
        Handles the selection of a countryball from the dropdown menu.
        """
        await interaction.response.defer(thinking=True)
        ball_instance = await BallInstance.get(
            id=int(interaction.data.get("values")[0])  # type: ignore
        )
        await self.ball_selected(interaction, ball_instance)

    async def ball_selected(self, interaction: discord.Interaction, ball_instance: BallInstance):
        """
        A placeholder method for handling selected countryballs.
        """
        raise NotImplementedError()


class CountryballsViewer(CountryballsSelector):
    """
    A specialized version of CountryballsSelector for viewing countryballs.

    Overrides the `ball_selected` method to handle displaying information
    about a selected countryball.
    """

    async def ball_selected(self, interaction: discord.Interaction, ball_instance: BallInstance):
        """
        Handles the display of a selected countryball.
        """
        content, file = await ball_instance.prepare_for_message(interaction)
        await interaction.followup.send(content=content, file=file)
        file.close()
