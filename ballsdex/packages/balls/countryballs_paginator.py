from __future__ import annotations

from typing import TYPE_CHECKING, List

import discord

from ballsdex.core.models import BallInstance
from ballsdex.core.utils import menus
from ballsdex.core.utils.paginator import Pages

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class CountryballsSource(menus.ListPageSource):
    def __init__(self, entries: List[BallInstance]):
        super().__init__(entries, per_page=25)

    async def format_page(self, menu: CountryballsSelector, balls: List[BallInstance]):
        menu.set_options(balls)
        return True  # signal to edit the page


class CountryballsSelector(Pages):
    def __init__(self, interaction: discord.Interaction["BallsDexBot"], balls: List[BallInstance]):
        self.bot = interaction.client
        source = CountryballsSource(balls)
        super().__init__(source, interaction=interaction)
        self.add_item(self.select_ball_menu)

    def set_options(self, balls: List[BallInstance]):
        options: List[discord.SelectOption] = []
        for ball in balls:
            if self.bot.cluster_count > 1:
                emoji = ball.ball.capacity_logic["emoji"]
            else:
                emoji = self.bot.get_emoji(int(ball.countryball.emoji_id))
            favorite = "❤️ " if ball.favorite else ""
            shiny = "✨ " if ball.shiny else ""
            special = ball.special_emoji(self.bot, True)
            custom_art = "🖼️" if "card" in ball.extra_data else ""
            options.append(
                discord.SelectOption(
                    label=f"{favorite}{shiny}{special}{custom_art}#{ball.pk:0X} {ball.countryball.country}",
                    description=f"ATK: {ball.attack_bonus:+d}% • HP: {ball.health_bonus:+d}% • "
                    f"Caught on {ball.catch_date.strftime('%d/%m/%y %H:%M')}",
                    emoji=emoji,
                    value=f"{ball.pk}",
                )
            )
        self.select_ball_menu.options = options

    @discord.ui.select()
    async def select_ball_menu(self, interaction: discord.Interaction, item: discord.ui.Select):
        await interaction.response.defer(thinking=True)
        ball_instance = await BallInstance.get(
            id=int(interaction.data.get("values")[0])  # type: ignore
        )
        await self.ball_selected(interaction, ball_instance)

    async def ball_selected(self, interaction: discord.Interaction, ball_instance: BallInstance):
        raise NotImplementedError()


class CountryballsViewer(CountryballsSelector):
    async def ball_selected(self, interaction: discord.Interaction, ball_instance: BallInstance):
        content, file = await ball_instance.prepare_for_message(interaction)
        await interaction.followup.send(content=content, file=file)
        file.close()
