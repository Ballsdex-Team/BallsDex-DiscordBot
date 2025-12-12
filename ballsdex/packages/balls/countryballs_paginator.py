from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator, List

import discord
from tortoise.expressions import RawSQL
from tortoise.functions import Count

from ballsdex.core.models import Ball, BallInstance, Player, Special
from ballsdex.core.utils import menus
from ballsdex.core.utils.paginator import Pages
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class CountryballsSource(menus.ListPageSource):
    def __init__(self, entries: list[int]):
        super().__init__(entries, per_page=25)
        self.cache: dict[int, BallInstance] = {}

    async def prepare(self):
        first_entries = (
            self.entries[: self.per_page * 5]
            if len(self.entries) > self.per_page * 5
            else self.entries
        )
        balls = await BallInstance.filter(id__in=first_entries)
        for ball in balls:
            self.cache[ball.pk] = ball

    async def fetch_page(self, ball_ids: list[int]) -> AsyncIterator[BallInstance]:
        if ball_ids[0] not in self.cache:
            async for ball in BallInstance.filter(id__in=ball_ids):
                self.cache[ball.pk] = ball
        for id in ball_ids:
            yield self.cache[id]

    async def format_page(self, menu: CountryballsSelector, ball_ids: list[int]):
        await menu.set_options(self.fetch_page(ball_ids))
        return True  # signal to edit the page


class CountryballsSelector(Pages):
    def __init__(self, interaction: discord.Interaction["BallsDexBot"], balls: list[int]):
        self.bot = interaction.client
        source = CountryballsSource(balls)
        super().__init__(source, interaction=interaction)
        self.add_item(self.select_ball_menu)

    async def set_options(self, balls: AsyncIterator[BallInstance]):
        options: List[discord.SelectOption] = []
        async for ball in balls:
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
    def __init__(self, interaction: discord.Interaction["BallsDexBot"], list, is_special: bool):
        self.bot = interaction.client
        self.is_special = is_special
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

        player = await Player.get(discord_id=interaction.user.id)
        balls_query = (
            BallInstance.filter(player=player)
            .annotate(
                total=RawSQL("COUNT(*)"),
                traded=RawSQL("SUM(CASE WHEN trade_player_id IS NULL THEN 0 ELSE 1 END)"),
            )
            .group_by("player_id")
        )
        countryball = None
        if self.is_special:
            special = await Special.get(name=item.values[0])
            balls_query = balls_query.filter(special=special).annotate(specials=RawSQL("1"))
            grouped_query = (
                BallInstance.filter(player=player, special=special)
                .prefetch_related("ball")
                .annotate(count=Count("id"))
                .group_by("ball__country", "ball__emoji_id")
            )
        else:
            countryball = await Ball.get(country=item.values[0])
            balls_query = balls_query.filter(ball=countryball).annotate(
                specials=RawSQL(
                    "SUM(CASE WHEN special_id IS NULL OR special_id IN "
                    "(SELECT id FROM special WHERE hidden = TRUE) THEN 0 ELSE 1 END)"
                ),
            )
            grouped_query = (
                BallInstance.filter(player=player, ball=countryball)
                .exclude(special=None)
                .exclude(special__hidden=True)
                .annotate(count=Count("id"))
                .group_by("special__name")
            )

        counts_list = await balls_query.values("player_id", "total", "traded", "specials")

        if not counts_list:
            await interaction.followup.send(
                f"You don't have any {settings.plural_collectible_name} yet."
            )
            return
        counts = counts_list[0]
        all_specials = await Special.filter(hidden=False)
        special_emojis = {x.name: x.emoji for x in all_specials}

        desc = (
            f"**Total**: {counts["total"]:,} ({counts["total"] - counts["traded"]:,} caught, "
            f"{counts['traded']:,} received from trade)\n"
        )
        if self.is_special:
            desc = f"**{settings.plural_collectible_name.title()}**: (Top 15)\n"
            countries = await grouped_query.values("ball__country", "ball__emoji_id", "count")
            for country in sorted(countries, key=lambda x: x["count"], reverse=True)[:15]:
                emoji = self.bot.get_emoji(country["ball__emoji_id"])
                desc += f"{emoji} {country["ball__country"]}: {country["count"]:,}\n"
        else:
            desc += f"**Total Specials**: {counts['specials']:,}\n"
            specials = await grouped_query.values("special__name", "count")
            if counts["specials"]:
                desc += "**Specials**:\n"
            for special in sorted(specials, key=lambda x: x["count"], reverse=True):
                emoji = special_emojis.get(special["special__name"], "")
                desc += f"{emoji} {special['special__name']}: {special["count"]:,}\n"

        embed = discord.Embed(
            title=f"{item.values[0]} Collection",
            description=desc,
            color=discord.Color.blurple(),
        )
        embed.set_author(
            name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url
        )
        if countryball:
            emoji = self.bot.get_emoji(countryball.emoji_id)
            if emoji:
                embed.set_thumbnail(url=emoji.url)
        await interaction.followup.send(embed=embed)
