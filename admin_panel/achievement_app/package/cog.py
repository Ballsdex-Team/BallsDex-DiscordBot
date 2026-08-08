from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Container, Section, Separator, TextDisplay, Thumbnail
from discord.utils import MISSING, format_dt
from django.db.models import Q

from ballsdex.core.discord import LayoutView
from ballsdex.core.utils.menus import ChunkedListSource, ItemFormatter, Menu
from bd_models.models import BallInstance, Friendship, Player, Trade, specials
from settings.models import settings
from settings.utils import format_currency

from ..checkers.instance import _handle_created_ballinstance
from ..models import Achievement as AchievementModel
from ..models import AchievementType, UserAchievement, progress_achievement
from ..transformers import AchievementTransform

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Achievement(commands.GroupCog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.checks.cooldown(1, 86400, key=lambda i: i.user.id)
    async def sync(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Synchronize your progress and claim any achievements you've earned
        """
        player = await Player.objects.aget_or_none(discord_id=interaction.user.id)

        if not player:
            await interaction.response.send_message(f"You're not registered in {settings.bot_name}", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        message = await interaction.followup.send(
            "Synchronizing achievements (it may take a few minutes)...", wait=True
        )
        unlocked = await self._sync_achievements(player)

        if not unlocked:
            await interaction.followup.send("You don't have any pending achievement.")
            return

        entries: list[TextDisplay | Section] = []
        for achievement in unlocked:
            if achievement.thumbnail:
                file = f"{settings.site_base_url}/media/{achievement.thumbnail.name}"
                section = Section(accessory=Thumbnail(file))
                title = TextDisplay(f"**{achievement.name}**")
                section.add_item(title)
                if achievement.description:
                    section.add_item(TextDisplay(achievement.description))
                if achievement.currency_reward:
                    section.add_item(TextDisplay(f"{format_currency(achievement.currency_reward, False, self.bot)}"))
                entries.append(section)
            else:
                text = TextDisplay(f"**{achievement.name}\n**")
                if achievement.description:
                    text.content += f"{achievement.description}\n"
                if achievement.currency_reward:
                    text.content += format_currency(achievement.currency_reward, False, self.bot)
                entries.append(text)

        view = LayoutView()
        view.add_item(TextDisplay(f"Synchronized! **{len(unlocked)}** have been completed."))
        container = Container()
        container.add_item(TextDisplay("# New Achievement(s) Unlocked!"))
        container.add_item(Separator())
        view.add_item(container)
        menu = Menu(interaction.client, view, ChunkedListSource(entries, 5), ItemFormatter(container, 1))
        await menu.init()
        await message.edit(content=None, view=view)

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
                        title.content += f" ✅\n**Completed At:** {format_dt(ua.completed_at)}"
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
                else:
                    text.content += "\n"
                if achievement.description:
                    text.content += f"{achievement.description}\n"
                if achievement.currency_reward:
                    text.content += format_currency(achievement.currency_reward, False, self.bot)
                if ua is not None and ua.completed_at:
                    text.content += f"**Completed at:** {format_dt(ua.completed_at)}"
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

    async def _sync_achievements(self, player: Player) -> list[AchievementModel]:
        unlocked = []

        all_achievements = [x async for x in AchievementModel.objects.prefetch_related("prerequisities").all()]
        existing_ua = {ua.achievement_id: ua async for ua in UserAchievement.objects.filter(player=player)}

        ball_instances = [x async for x in BallInstance.all_objects.filter(player=player)]
        trades = [x async for x in Trade.objects.filter(Q(player1=player) | Q(player2=player))]
        friendships = [x async for x in Friendship.objects.filter(Q(player1=player) | Q(player2=player))]

        trade_player_ids = {i.trade_player_id for i in ball_instances if i.trade_player_id}
        trade_players = (
            {p.pk: p async for p in Player.objects.filter(pk__in=trade_player_ids)} if trade_player_ids else {}
        )

        async def run(achievement_type, **context):
            return await progress_achievement(
                player, achievement_type, achievements=all_achievements, existing_ua=existing_ua, **context
            )

        for t in (
            AchievementType.BALL_COUNT,
            AchievementType.COMPLETE_GROUP,
            AchievementType.COMPLETION_PERCENTAGE,
            AchievementType.PLAYTIME,
        ):
            unlocked += await run(t)

        special_ids = {i.special_id for i in ball_instances if i.special_id}
        for special_id in special_ids:
            if special := specials.get(special_id):
                unlocked += await run(AchievementType.FIRST_SPECIAL, special=special)

        for instance in ball_instances:
            unlocked += await run(AchievementType.FIRST_CATCH)
            unlocked += await run(AchievementType.CATCH_BALL, instance=instance)
            if instance.catch_date and instance.spawned_time:
                elapsed = (instance.catch_date - instance.spawned_time).total_seconds()
                unlocked += await run(AchievementType.FASTEST_CATCHER, elapsed_seconds=elapsed)
            if instance.trade_player_id is not None:
                trade_player = trade_players.get(instance.trade_player_id)
                if trade_player:
                    unlocked += await run(AchievementType.RECEIVE_BALL, user_id=trade_player.discord_id)
            if instance.favorite:
                unlocked += await run(AchievementType.FIRST_FAVORITE_BALL)

        for trade in trades:
            received = trade.player2_money if trade.player1_id == player.pk else trade.player1_money
            unlocked += await run(AchievementType.COMPLETE_TRADE, received_currency=received)
            unlocked += await run(AchievementType.FIRST_TRADE)

        for _ in friendships:
            unlocked += await run(AchievementType.FIRST_FRIEND)
            unlocked += await run(AchievementType.HAVE_FRIEND)

        return unlocked
