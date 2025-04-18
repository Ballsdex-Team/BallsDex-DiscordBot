from __future__ import annotations

from typing import TYPE_CHECKING, List

import discord

from ballsdex.core.models import BallInstance
from ballsdex.core.utils import menus
from ballsdex.core.utils.paginator import Pages
from ballsdex.settings import settings

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
            emoji = self.bot.get_emoji(int(ball.countryball.emoji_id))
            favorite = f"{settings.favorited_collectible_emoji} " if ball.favorite else ""
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
    async def select_ball_menu(
        self, interaction: discord.Interaction["BallsDexBot"], item: discord.ui.Select
    ):
        await interaction.response.defer(thinking=True)
        ball_instance = await BallInstance.get(
            id=int(interaction.data.get("values")[0])  # type: ignore
        )
        await self.ball_selected(interaction, ball_instance)

    async def ball_selected(
        self, interaction: discord.Interaction["BallsDexBot"], ball_instance: BallInstance
    ):
        raise NotImplementedError()


class CountryballsViewer(CountryballsSelector):
    async def ball_selected(
        self, interaction: discord.Interaction["BallsDexBot"], ball_instance: BallInstance
    ):
        content, file, view = await ball_instance.prepare_for_message(interaction)
        await interaction.followup.send(content=content, file=file, view=view)
        file.close()


class DuplicateSource(menus.ListPageSource):
    def __init__(self, entries: List[str]):
        super().__init__(entries, per_page=25)

    async def format_page(self, menu, items):
        menu.set_options(items)
        return True  # signal to edit the page


class DuplicateViewMenu(Pages):
    def __init__(self, interaction: discord.Interaction["BallsDexBot"], list, dupe_type: str):
        self.bot = interaction.client
        self.dupe_type = dupe_type
        source = DuplicateSource(list)
        super().__init__(source, interaction=interaction)
        self.add_item(self.dupe_ball_menu)

    def set_options(self, items):
        options: List[discord.SelectOption] = []
        for item in items:
            options.append(
                discord.SelectOption(
                    label=item["name"], description=f"Count: {item['count']}", emoji=item["emoji"]
                )
            )
        self.dupe_ball_menu.options = options

    @discord.ui.select()
    async def dupe_ball_menu(self, interaction: discord.Interaction, item: discord.ui.Select):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if self.dupe_type == settings.plural_collectible_name:
            balls = await BallInstance.filter(
                ball__country=item.values[0], player__discord_id=interaction.user.id
            ).count()
        else:
            balls = await BallInstance.filter(
                special__name=item.values[0], player__discord_id=interaction.user.id
            ).count()

        plural = settings.collectible_name if balls == 1 else settings.plural_collectible_name
        await interaction.followup.send(f"You have {balls:,} {item.values[0]} {plural}.")
