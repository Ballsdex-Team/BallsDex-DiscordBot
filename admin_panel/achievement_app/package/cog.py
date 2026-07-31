from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Container, Section, Separator, TextDisplay, Thumbnail
from discord.utils import MISSING, format_dt

from ballsdex.core.discord import LayoutView
from ballsdex.core.utils.menus import ChunkedListSource, ItemFormatter, Menu
from bd_models.models import Player
from settings.models import settings
from settings.utils import format_currency

from ..models import Achievement as AchievementModel
from ..models import UserAchievement
from ..transformers import AchievementTransform

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Achievement(commands.GroupCog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    async def list(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Show the list of available achievements.
        """
        player = await Player.objects.aget_or_none(discord_id=interaction.user.id)

        if not player:
            await interaction.response.send_message(f"You're not registered in {settings.bot_name}", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        achievements = [x async for x in AchievementModel.objects.all()]
        user_achievements = {ua.achievement_id: ua async for ua in UserAchievement.objects.filter(player=player)}
        completed_achievements = {key: value for key, value in user_achievements.items() if value.completed}

        entries: list[TextDisplay | Section] = []
        for achievement in achievements:
            ua = user_achievements.get(achievement.pk)
            if achievement.thumbnail:
                file = f"{settings.site_base_url}/media/{achievement.thumbnail.name}"
                section = Section(accessory=Thumbnail(file))
                title = TextDisplay(f"**{achievement.name}**")
                if ua is not None:
                    if ua.completed_at:
                        title.content += " ✅"
                    else:
                        title.content += f" ({ua.progress}/{achievement.target_value})"
                section.add_item(title)
                if achievement.description:
                    section.add_item(TextDisplay(achievement.description))
                if achievement.currency_reward:
                    section.add_item(TextDisplay(f"{format_currency(achievement.currency_reward, False, self.bot)}"))
                entries.append(section)
            else:
                text = TextDisplay(f"**{achievement.name}**")
                if ua is not None:
                    if ua.completed_at:
                        text.content += " ✅\n"
                    else:
                        text.content += f" ({ua.progress}/{achievement.target_value})\n"
                if achievement.description:
                    text.content += f"{achievement.description}\n"
                if achievement.currency_reward:
                    text.content += format_currency(achievement.currency_reward, False, self.bot)
                entries.append(text)

        percentage = round((len(completed_achievements) / len(achievements)) * 100)
        view = LayoutView()
        view.restrict_author(interaction.user.id)
        container = Container()
        container.add_item(TextDisplay(f"# {settings.bot_name} Achievements"))
        container.add_item(TextDisplay(f"{len(completed_achievements)}/{len(achievements)} ({percentage}%)"))
        container.add_item(Separator())
        view.add_item(container)
        menu = Menu(interaction.client, view, ChunkedListSource(entries, 5), ItemFormatter(container, 2))
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

        if not player:
            await interaction.response.send_message(f"You're not registered in {settings.bot_name}", ephemeral=True)
            return

        user_achievement, _ = await UserAchievement.objects.aget_or_create(player=player, achievement=achievement)

        container = Container()
        container.add_item(TextDisplay(f"# {achievement.name}"))
        container.add_item(Separator())
        if achievement.thumbnail:
            file = discord.File(achievement.thumbnail.path, achievement.thumbnail.name)
            section = Section(accessory=Thumbnail(file))
            if achievement.description:
                section.add_item(TextDisplay(achievement.description))
            if achievement.currency_reward:
                section.add_item(TextDisplay(f"**Reward:** {achievement.currency_reward}"))
            if user_achievement.completed_at:
                section.add_item(TextDisplay(f"**Unlocked at:** {format_dt(user_achievement.completed_at)}"))
            else:
                section.add_item(TextDisplay(f"**Progress:** {user_achievement.progress}/{achievement.target_value}"))
            container.add_item(section)
        else:
            file = MISSING
            if achievement.description:
                container.add_item(TextDisplay(achievement.description))
            if achievement.currency_reward:
                container.add_item(TextDisplay(f"**Reward:** {achievement.currency_reward}"))
            if user_achievement.completed_at:
                container.add_item(TextDisplay(f"**Unlocked at:** {format_dt(user_achievement.completed_at)}"))
            else:
                container.add_item(TextDisplay(f"**Progress:** {user_achievement.progress}/{achievement.target_value}"))

        view = LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view, file=file)
