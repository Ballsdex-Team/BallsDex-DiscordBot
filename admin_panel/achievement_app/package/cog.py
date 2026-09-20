from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Separator, TextDisplay
from discord.utils import format_dt
from django.db.models import Q

from ballsdex.core.discord import Container, LayoutView
from ballsdex.core.utils.menus import ChunkedListSource, ItemFormatter, Menu
from bd_models.models import Player
from settings.models import settings

from ..engine import engine
from ..models import Achievement as AchievementModel
from ..models import UserAchievement
from ..notifications import achievement_item
from ..transformers import AchievementCategoryTransform, AchievementTransform

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from bd_models.models import Player as PlayerModel

    from ..models import AchievementCategory


def progress_bar(progress: int, target: int, length: int = 10) -> str:
    filled = min(length, progress * length // max(target, 1))
    return "\N{BLACK PARALLELOGRAM}" * filled + "\N{WHITE PARALLELOGRAM}" * (length - filled)


class Achievement(commands.GroupCog):
    """
    Check your achievements.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    async def _visible_achievements(
        self, player: "PlayerModel | None", category: "AchievementCategory | None"
    ) -> tuple[list[AchievementModel], dict[int, UserAchievement]]:
        user_achievements = (
            {ua.achievement_id: ua async for ua in UserAchievement.objects.filter(player=player)} if player else {}
        )
        unlocked_ids = [achievement_id for achievement_id, ua in user_achievements.items() if ua.completed]
        # retired achievements stay visible to the players who unlocked them
        queryset = AchievementModel.objects.filter(
            Q(status=AchievementModel.Status.ACTIVE) | Q(status=AchievementModel.Status.RETIRED, pk__in=unlocked_ids)
        ).select_related("ball", "special", "group", "category")
        if category:
            queryset = queryset.filter(category=category)
        return [achievement async for achievement in queryset], user_achievements

    @app_commands.command(name="list")
    @app_commands.choices(
        show=[
            app_commands.Choice(name="All achievements", value="all"),
            app_commands.Choice(name="Unlocked only", value="unlocked"),
            app_commands.Choice(name="Locked only", value="locked"),
        ],
        sort=[
            app_commands.Choice(name="Default order", value="default"),
            app_commands.Choice(name="Recently unlocked first", value="recent"),
            app_commands.Choice(name="Oldest unlocked first", value="oldest"),
            app_commands.Choice(name="Closest to unlock first", value="progress"),
        ],
    )
    async def achievement_list(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        show: app_commands.Choice[str] | None = None,
        sort: app_commands.Choice[str] | None = None,
        category: AchievementCategoryTransform | None = None,
    ):
        """
        Show the list of achievements and your progress.

        Parameters
        ----------
        show: str
            Show every achievement, or only the unlocked or locked ones.
        sort: str
            How to order the achievements.
        category: AchievementCategory
            Only show the achievements of this category.
        """
        await interaction.response.defer(thinking=True)
        player = await Player.objects.aget_or_none(discord_id=interaction.user.id)
        achievements, user_achievements = await self._visible_achievements(player, category)
        if not achievements:
            await interaction.followup.send("There are no achievements to show yet.", ephemeral=True)
            return

        def is_unlocked(achievement: AchievementModel) -> bool:
            ua = user_achievements.get(achievement.pk)
            return ua is not None and ua.completed

        def unlocked_at(achievement: AchievementModel) -> datetime:
            ua = user_achievements.get(achievement.pk)
            return (ua.completed_at if ua else None) or datetime.min.replace(tzinfo=UTC)

        def ratio(achievement: AchievementModel) -> float:
            ua = user_achievements.get(achievement.pk)
            return (ua.progress if ua else 0) / engine.target(achievement)

        unlocked = [achievement for achievement in achievements if is_unlocked(achievement)]
        locked = [achievement for achievement in achievements if not is_unlocked(achievement)]
        total, unlocked_count = len(achievements), len(unlocked)

        match sort.value if sort else "default":
            case "recent":
                unlocked.sort(key=unlocked_at, reverse=True)
                ordered = unlocked + locked
            case "oldest":
                unlocked.sort(key=unlocked_at)
                ordered = unlocked + locked
            case "progress":
                locked.sort(key=ratio, reverse=True)
                ordered = locked + unlocked
            case _:
                ordered = achievements
        if show and show.value == "unlocked":
            ordered = [achievement for achievement in ordered if is_unlocked(achievement)]
        elif show and show.value == "locked":
            ordered = [achievement for achievement in ordered if not is_unlocked(achievement)]
        if not ordered:
            await interaction.followup.send(
                "You haven't unlocked any achievement yet!"
                if show and show.value == "unlocked"
                else "You unlocked every achievement, congratulations!",
                ephemeral=True,
            )
            return

        entries = [self._entry(achievement, user_achievements.get(achievement.pk)) for achievement in ordered]
        percentage = round(unlocked_count * 100 / total)
        subtitle = f"-# {unlocked_count}/{total} unlocked ({percentage}%)"
        if category:
            subtitle += f" • {category}"
        view = LayoutView()
        view.restrict_author(interaction.user.id)
        container = Container(
            TextDisplay(f"# {interaction.user.display_name}'s {settings.bot_name} achievements"),
            TextDisplay(subtitle),
            Separator(),
            accent_colour=settings.embed_colour,
        )
        view.add_item(container)
        menu = Menu(self.bot, view, ChunkedListSource(entries, 5), ItemFormatter(container, 2))
        await menu.init()
        await interaction.followup.send(view=view)

    def _entry(self, achievement: AchievementModel, ua: UserAchievement | None) -> discord.ui.Item:
        if ua and ua.completed:
            unlocked = f" • unlocked {format_dt(ua.completed_at, 'R')}" if ua.completed_at else ""
            heading = f"\N{WHITE HEAVY CHECK MARK} **{achievement.name}**{unlocked}"
            return achievement_item(self.bot, achievement, heading=heading)
        if achievement.hidden:
            return TextDisplay("\N{BLACK QUESTION MARK ORNAMENT} **Secret achievement**\nKeep playing to discover it!")
        target = engine.target(achievement)
        progress = ua.progress if ua else 0
        heading = f"\N{LOCK} **{achievement.name}** • {progress}/{target} {progress_bar(progress, target)}"
        return achievement_item(self.bot, achievement, heading=heading)

    @app_commands.command()
    @app_commands.checks.cooldown(1, 300, key=lambda i: i.user.id)
    async def sync(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Refresh your progress and claim the achievements you already earned.
        """
        await interaction.response.defer(thinking=True)
        player = await Player.objects.aget_or_none(discord_id=interaction.user.id)
        if player is None:
            await interaction.followup.send(f"You're not registered in {settings.bot_name}.", ephemeral=True)
            return

        unlocked = await engine.sync_player(player)
        if not unlocked:
            await interaction.followup.send(
                "Your progress is up to date, you don't have any pending achievement.\n"
                "-# Achievements counting actions, like catches or trades, are counted when you play.",
                ephemeral=True,
            )
            return

        view = LayoutView()
        container = Container(
            TextDisplay(f"## \N{TROPHY} {len(unlocked)} achievement(s) unlocked!"),
            Separator(),
            accent_colour=settings.embed_colour,
        )
        view.add_item(container)
        entries = [achievement_item(self.bot, achievement) for achievement in unlocked]
        menu = Menu(self.bot, view, ChunkedListSource(entries, 5), ItemFormatter(container, 2))
        await menu.init()
        await interaction.followup.send(view=view)

    @app_commands.command()
    async def info(self, interaction: discord.Interaction["BallsDexBot"], achievement: AchievementTransform):
        """
        Check your progress in a specific achievement.

        Parameters
        ----------
        achievement: Achievement
            The achievement to check.
        """
        player = await Player.objects.aget_or_none(discord_id=interaction.user.id)
        ua = await UserAchievement.objects.filter(player=player, achievement=achievement).afirst() if player else None
        target = engine.target(achievement)

        if ua and ua.completed:
            status = "\N{WHITE HEAVY CHECK MARK} Unlocked" + (
                f" {format_dt(ua.completed_at)}" if ua.completed_at else ""
            )
        elif achievement.status == AchievementModel.Status.RETIRED:
            status = "\N{NO ENTRY SIGN} This achievement can't be unlocked anymore."
        else:
            progress = ua.progress if ua else 0
            status = f"**Progress:** {progress}/{target} {progress_bar(progress, target)}"
        unlocked_by = await UserAchievement.objects.filter(achievement=achievement, completed=True).acount()
        details = f"{status}\n-# Unlocked by {unlocked_by:,} player{'s' if unlocked_by != 1 else ''}"
        if achievement.category:
            details += f" • {achievement.category}"

        view = LayoutView()
        view.add_item(
            Container(
                TextDisplay(f"# {achievement.name}"),
                Separator(),
                achievement_item(self.bot, achievement, heading="", details=details),
                accent_colour=settings.embed_colour,
            )
        )
        await interaction.response.send_message(view=view)
