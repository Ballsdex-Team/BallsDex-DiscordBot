from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, List

import discord

from ballsdex.core.models import Ball, BallInstance, Special
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
        type = None
        if self.dupe_type == settings.plural_collectible_name:
            balls = await BallInstance.filter(
                ball__country=item.values[0], player__discord_id=interaction.user.id
            ).prefetch_related("special")
            type = "country"
        else:
            balls = await BallInstance.filter(
                special__name=item.values[0], player__discord_id=interaction.user.id
            )
            type = "special"

        total = len(balls)
        total_traded = len([x for x in balls if x.trade_player])
        total_caught_self = total - total_traded
        if type == "country":
            special_count = len([x for x in balls if x.special])
            specials = defaultdict(int)
            all_specials = await Special.filter(hidden=False)
            special_emojis = {x.name: x.emoji for x in all_specials}
            for ball in balls:
                if ball.special:
                    specials[ball.special] += 1

            desc = (
                f"**Total**: {total:,} ({total_caught_self:,} caught, "
                f"{total_traded:,} received from trade)\n"
                f"**Total Specials**: {special_count:,}\n\n"
            )
            if specials:
                desc += "**Specials**:\n"
            for special, count in sorted(specials.items(), key=lambda x: x[1], reverse=True):
                emoji = special_emojis.get(special.name, "")
                desc += f"{emoji} {special.name}: {count:,}\n"
        else:
            desc = (
                f"**Total**: {total:,} ({total_caught_self:,} caught, "
                f"{total_traded:,} received from trade)\n\n"
            )
            countries = defaultdict(int)
            for ball in balls:
                countries[ball.countryball] += 1
            desc = "**Countries**: (Top 15)\n"
            for country, count in sorted(countries.items(), key=lambda x: x[1], reverse=True)[:15]:
                emoji = self.bot.get_emoji(country.emoji_id)
                desc += f"{emoji} {country}: {count:,}\n"

        embed = discord.Embed(
            title=f"{item.values[0]} Collection",
            description=desc,
            color=discord.Color.blurple(),
        )
        embed.set_author(
            name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url
        )
        if type == "country":
            countryball = await Ball.get(country=item.values[0])
            emoji = self.bot.get_emoji(countryball.emoji_id)
            if emoji:
                embed.set_thumbnail(url=emoji.url)
        await interaction.followup.send(embed=embed, ephemeral=True)
