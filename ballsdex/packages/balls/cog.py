import enum
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Container, LayoutView, TextDisplay
from django.db.models import Count, Exists, F, OuterRef, Q
from django.utils import timezone

from ballsdex.core.discord import LayoutView as TrackedLayoutView
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.menus import ChunkedListSource, Menu, SelectFormatter, TextFormatter, TextSource
from ballsdex.core.utils.sorting import FilteringChoices, SortingChoices, filter_balls, sort_balls
from ballsdex.core.utils.transformers import (
    BallEnabledTransform,
    BallGroupTransform,
    BallInstanceTransform,
    EconomyTransform,
    RegimeTransform,
    SpecialEnabledTransform,
    TradeCommandType,
)
from ballsdex.core.utils.utils import can_mention, inventory_privacy, is_staff
from bd_models.enums import DonationPolicy
from bd_models.models import BallInstance, Player, Special, Trade, TradeObject, balls, groups
from settings.models import settings

from .bulk_give_selector import BulkGiveSelector
from .countryballs_paginator import CountryballsDuplicateSource, CountryballsViewer
from .donation import DonationRequest, GiveSkipReason, check_giveable, check_recipient

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from ballsdex.packages.countryballs.cog import CountryBallsSpawner

log = logging.getLogger("ballsdex.packages.countryballs")


class DuplicateType(enum.StrEnum):
    countryballs = settings.plural_collectible_name
    specials = "specials"


class DuplicateSort(enum.Enum):
    count_desc = "-count"
    count_asc = "count"
    alphabetic = "name"
    alphabetic_reverse = "-name"
    rarity = "rarity"
    rarity_reverse = "-rarity"


class Balls(commands.GroupCog, group_name=settings.balls_slash_name):
    """
    View and manage your countryballs collection.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
    async def list(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User | None = None,
        sort: SortingChoices | None = None,
        reverse: bool = False,
        countryball: BallEnabledTransform | None = None,
        economy: EconomyTransform | None = None,
        regime: RegimeTransform | None = None,
        special: SpecialEnabledTransform | None = None,
        filter: FilteringChoices | None = None,
        group: BallGroupTransform | None = None,
        ephemeral: bool = False,
    ):
        """
        List your countryballs.

        Parameters
        ----------
        user: discord.User
            The user whose collection you want to view, if not yours.
        sort: SortingChoices
            Choose how countryballs are sorted. Can be used to show duplicates.
        reverse: bool
            Reverse the output of the list.
        countryball: Ball
            Filter the list by a specific countryball.
        regime: Regime
            Filter the list by a specific regime.
        economy: Economy
            Filter the list by a specific economy.
        special: Special
            Filter the list by a specific special event.
        filter: FilteringChoices
            Filter the list by a specific filter.
        group: BallGroup
            Filter the list by a specific group.
        ephemeral: bool
            Whether or not to send the command ephemerally.
        """
        user_obj = user or interaction.user
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)

        try:
            player = await Player.objects.aget(discord_id=user_obj.id)
        except Player.DoesNotExist:
            if user_obj == interaction.user:
                await interaction.followup.send(f"You don't have any {settings.plural_collectible_name} yet.")
            else:
                await interaction.followup.send(
                    f"{user_obj.name} doesn't have any {settings.plural_collectible_name} yet."
                )
            return
        staff = await is_staff(interaction)
        if user is not None:
            if user.id in self.bot.blacklist and not staff:
                await interaction.followup.send("You cannot view the inventory of a blacklisted user.", ephemeral=True)
                return
            if await inventory_privacy(self.bot, interaction, player, user_obj) is False:
                return

        interaction_player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)

        blocked = await player.is_blocked(interaction_player)
        if blocked and not staff:
            await interaction.followup.send("You cannot view the list of a user that has you blocked.", ephemeral=True)
            return

        query = BallInstance.objects.filter(player=player).prefetch_related("trade_player")
        if filter:
            query = filter_balls(filter, query, interaction.guild_id)
        if countryball:
            query = query.filter(ball=countryball)
        if regime:
            query = query.filter(ball__regime=regime)
        if economy:
            query = query.filter(ball__economy=economy)
        if special:
            query = query.filter(special=special)
        if group:
            query = query.filter(ball__groups=group)
        if sort:
            query = sort_balls(sort, query)
        else:
            query = query.order_by("-favorite")
        query.query.add_ordering("-id")  # enforce a unique ordering to prevent mismatch during pagination

        if not await query.aexists():
            ball_txt = countryball.country if countryball else ""
            special_txt = special.name if special else ""
            group_txt = group.name if group else ""

            combined = " ".join(x for x in (special_txt, group_txt, ball_txt) if x)
            combined_txt = f"{combined} " if combined else ""
            if user_obj == interaction.user:
                await interaction.followup.send(
                    f"You don't have any {combined_txt}{settings.plural_collectible_name} yet."
                )
            else:
                await interaction.followup.send(
                    f"{user_obj.name} doesn't have any {combined_txt}{settings.plural_collectible_name} yet."
                )
            return
        if reverse:
            query = query.reverse()

        view = CountryballsViewer(ephemeral=ephemeral)
        view.restrict_author(interaction.user.id)
        menu = Menu.countryballs(self.bot, view, view.selected, query)
        await menu.init()
        if user_obj != interaction.user:
            view.header.content = f"Viewing {user_obj.name}'s {settings.plural_collectible_name}"
        else:
            view.header.content = f"Viewing your {settings.plural_collectible_name}"
        await interaction.followup.send(view=view)

    @app_commands.command()
    @app_commands.checks.cooldown(1, 20, key=lambda i: i.user.id)
    async def completion(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User | None = None,
        special: SpecialEnabledTransform | None = None,
        filter: FilteringChoices | None = None,
        regime: RegimeTransform | None = None,
        economy: EconomyTransform | None = None,
        group: BallGroupTransform | None = None,
        duplicates: bool = False,
        ephemeral: bool = False,
    ):
        """
        Show your current completion of the BallsDex.

        Parameters
        ----------
        user: discord.User
            The user whose completion you want to view, if not yours.
        special: Special
            The special you want to see the completion of
        filter: FilteringChoices
            Filter the list by a specific filter.
        regime: Regime
            The regime you want to see the completion of
        economy: Economy
            The economy you want to see the completion of
        group: BallGroup
            The group you want to see the completion of
        duplicates: bool
            Show the completion of duplicates.
        ephemeral: bool
            Whether or not to send the command ephemerally.
        """
        user_obj = user or interaction.user
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        extra_text = f"{special.name} " if special else ""
        if regime:
            extra_text += f"{regime.name} "
        if economy:
            extra_text += f"{economy.name} "
        if group:
            extra_text += f"{group.name} "
        if user is not None:
            try:
                player = await Player.objects.aget(discord_id=user_obj.id)
            except Player.DoesNotExist:
                await interaction.followup.send(
                    f"{user_obj.name} doesn't have any {extra_text}{settings.plural_collectible_name} yet."
                )
                return
            staff = await is_staff(interaction)
            if user.id in self.bot.blacklist and not staff:
                await interaction.followup.send("You cannot view the completion of a blacklisted user.", ephemeral=True)
                return

            interaction_player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)

            blocked = await player.is_blocked(interaction_player)
            if blocked and not staff:
                await interaction.followup.send(
                    "You cannot view the completion of a user that has blocked you.", ephemeral=True
                )
                return

            if await inventory_privacy(self.bot, interaction, player, user_obj) is False:
                return
        # Filter disabled balls, they do not count towards progression
        # Only ID and emoji is interesting for us
        bot_countryballs = {x: y.emoji_id for x, y in balls.items() if y.enabled}

        # Set of ball IDs owned by the player
        filters = {"player__discord_id": user_obj.id, "ball__enabled": True}
        if special:
            filters["special"] = special
            bot_countryballs = {
                x: y.emoji_id
                for x, y in balls.items()
                if y.enabled and (special.end_date is None or y.created_at is None or y.created_at < special.end_date)
            }

        if regime:
            filters["ball__regime"] = regime
            bot_countryballs = {x: y for x, y in bot_countryballs.items() if balls[x].regime_id == regime.pk}

        if economy:
            filters["ball__economy"] = economy
            bot_countryballs = {x: y for x, y in bot_countryballs.items() if balls[x].economy_id == economy.pk}

        if group:
            filters["ball__groups"] = group
            group_ball_ids = {ball.pk for ball in groups[group.pk].balls} if group.pk in groups else set()
            bot_countryballs = {x: y for x, y in bot_countryballs.items() if x in group_ball_ids}

        if filter:
            query = filter_balls(filter, BallInstance.objects.filter(**filters), interaction.guild_id)
        else:
            query = BallInstance.objects.filter(**filters)

        if not bot_countryballs:
            await interaction.followup.send(
                f"There are no {extra_text}{settings.plural_collectible_name} registered on this bot yet.",
                ephemeral=True,
            )
            return

        if duplicates:
            query = query.values("ball_id").annotate(count=Count("ball_id")).filter(count__gt=1)

        owned_countryballs = set(
            [
                x[0]
                async for x in query.filter(**filters)
                .distinct()  # Do not query everything
                .values_list("ball_id")
            ]
        )

        special_str = f" ({special.name})" if special else ""
        regime_str = f" ({regime.name})" if regime else ""
        economy_str = f" ({economy.name})" if economy else ""
        group_str = f" ({group.name})" if group else ""
        original_catcher_string = " " + filter.value.replace("_", " ") + " " if filter else ""
        duplicates_str = " duplicates" if duplicates else ""
        progression = round(len(owned_countryballs) / len(bot_countryballs) * 100, 1)
        text = (
            f"## {settings.bot_name}{original_catcher_string}"
            f"{special_str}{regime_str}{economy_str}{group_str}{duplicates_str} progression: "
            f"**{progression}%**\n"
        )

        def fill_fields(title: str, emoji_ids: set[int]):
            nonlocal text
            text += f"### {title}\n"
            if not emoji_ids:
                text += "Nothing yet.\n"
                return
            for emoji_id in emoji_ids:
                emoji = self.bot.get_emoji(emoji_id)
                if not emoji:
                    continue
                text += f"{emoji} "
            text += "\n"

        # Getting the list of emoji IDs from the IDs of the owned countryballs
        fill_fields(f"Owned {settings.plural_collectible_name}", set(bot_countryballs[x] for x in owned_countryballs))

        if missing := set(y for x, y in bot_countryballs.items() if x not in owned_countryballs):
            fill_fields(f"Missing {settings.plural_collectible_name}", missing)
        else:
            text += f"### :tada: No missing {settings.plural_collectible_name}, congratulations! :tada:"

        view = LayoutView()
        container = Container()
        if user is not None and user != interaction.user:
            header = TextDisplay(f"Viewing {user_obj.display_name}'s completion")
            container.add_item(header)
        display = TextDisplay("")
        container.add_item(display)
        view.add_item(container)
        menu = Menu(self.bot, view, TextSource(text, delims=[" \n###", " "]), TextFormatter(display))
        await menu.init()
        await interaction.followup.send(view=view)

    @app_commands.command()
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def info(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
        ephemeral: bool = False,
    ):
        """
        Display info from a specific countryball.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to inspect
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        ephemeral: bool
            Whether or not to send the command ephemerally.
        """
        if not countryball:
            return
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        content, file, view = await countryball.prepare_for_message(interaction)
        await interaction.followup.send(content=content, file=file, view=view)
        file.close()

    @app_commands.command()
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def last(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User | None = None,
        filter: FilteringChoices | None = None,
        index: app_commands.Range[int, 1] = 1,
    ):
        """
        Display info of your or another users last caught countryball.

        Parameters
        ----------
        user: discord.Member
            The user you would like to see
        filter: FilteringChoices
            Filter the last caught countryball by a specific filter.
            Only works if the user has caught at least one countryball.
        index: int
            How far back to look. 1 is the most recent catch, 2 the one before that, and so on.
        """
        user_obj = user if user else interaction.user
        await interaction.response.defer(thinking=True)
        try:
            player = await Player.objects.aget(discord_id=user_obj.id)
        except Player.DoesNotExist:
            msg = f"{'You do' if user is None else f'{user_obj.display_name} does'}"
            await interaction.followup.send(
                f"{msg} not have any {settings.plural_collectible_name} yet.", ephemeral=True
            )
            return

        staff = await is_staff(interaction)
        if user is not None:
            if user.id in self.bot.blacklist and not staff:
                await interaction.followup.send(
                    (f"You cannot view the last caught {settings.collectible_name} of a blacklisted user."),
                    ephemeral=True,
                )
                return
            if await inventory_privacy(self.bot, interaction, player, user_obj) is False:
                return

        interaction_player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)

        blocked = await player.is_blocked(interaction_player)
        if blocked and not staff:
            await interaction.followup.send(
                f"You cannot view the last caught {settings.collectible_name} of a user that has blocked you.",
                ephemeral=True,
            )
            return

        query = player.balls.select_related("ball", "trade_player").all()
        filter_msg = ""
        if filter:
            filter_msg = f" with the `{filter.value.replace('_', ' ')}` filter"
            query = filter_balls(filter, query, interaction.guild_id)
        matches = [cb async for cb in query.order_by("-id")[index - 1 : index]]
        countryball = matches[0] if matches else None
        if not countryball:
            if index == 1:
                msg = f"{'You do' if user is None else f'{user_obj.display_name} does'}"
                await interaction.followup.send(
                    f"{msg} not have any {settings.plural_collectible_name} yet.", ephemeral=True
                )
            else:
                who = "You don't" if user is None else f"{user_obj.display_name} doesn't"
                await interaction.followup.send(
                    f"{who} have {index} caught {settings.plural_collectible_name}{filter_msg} yet.", ephemeral=True
                )
            return

        index_msg = "" if index == 1 else f" ({index} catches back)"
        content, file, view = await countryball.prepare_for_message(interaction)
        if user is not None and user.id != interaction.user.id:
            content = (
                f"You are viewing {user.display_name}'s last caught "
                f"{settings.collectible_name}{filter_msg}{index_msg}.\n{content}"
            )
        else:
            content = (
                f"You are viewing your last caught {settings.collectible_name}{filter_msg}{index_msg}.\n" + content
            )
        await interaction.followup.send(content=content, file=file, view=view)
        file.close()

    @app_commands.command()
    async def favorite(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Set favorite countryballs.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to set/unset as favorite
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        """
        if not countryball:
            return

        if settings.max_favorites == 0:
            await interaction.response.send_message(
                f"You cannot set favorite {settings.plural_collectible_name} in this bot."
            )
            return

        if not countryball.favorite:
            try:
                player = await Player.objects.aget(discord_id=interaction.user.id)
            except Player.DoesNotExist:
                await interaction.response.send_message(
                    f"You don't have any {settings.plural_collectible_name} yet.", ephemeral=True
                )
                return

            grammar = (
                f"{settings.collectible_name}" if settings.max_favorites == 1 else f"{settings.plural_collectible_name}"
            )
            if await player.balls.filter(favorite=True).acount() >= settings.max_favorites:
                await interaction.response.send_message(
                    f"You cannot set more than {settings.max_favorites} favorite {grammar}.", ephemeral=True
                )
                return

            countryball.favorite = True  # type: ignore
            await countryball.asave()
            emoji = self.bot.get_emoji(countryball.countryball.emoji_id) or ""
            await interaction.response.send_message(
                f"{emoji} `#{countryball.pk:0X}` {countryball.countryball.country} "
                f"is now a favorite {settings.collectible_name}!",
                ephemeral=True,
            )

        else:
            countryball.favorite = False  # type: ignore
            await countryball.asave()
            emoji = self.bot.get_emoji(countryball.countryball.emoji_id) or ""
            await interaction.response.send_message(
                f"{emoji} `#{countryball.pk:0X}` {countryball.countryball.country} "
                f"isn't a favorite {settings.collectible_name} anymore.",
                ephemeral=True,
            )

    @app_commands.command()
    @app_commands.checks.cooldown(1, 180, key=lambda i: i.user.id)
    async def drop(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Drop one of your countryballs back into the wild, to be caught again.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to drop
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        """
        if not countryball:
            return

        cog = cast("CountryBallsSpawner | None", self.bot.get_cog("CountryBallsSpawner"))

        if not countryball.is_tradeable:
            await interaction.response.send_message(
                f"You cannot drop this {settings.collectible_name}.", ephemeral=True
            )
            return

        if await countryball.is_locked():
            await interaction.response.send_message(
                f"This {settings.collectible_name} is currently locked for a trade. Please try again later.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            ball = await cog.countryball_cls.from_existing(self.bot, countryball)
        except RuntimeError:
            await interaction.followup.send(
                f"This {settings.collectible_name} is currently locked for a trade. Please try again later.",
                ephemeral=True,
            )
            return

        result = await ball.spawn(interaction.channel)  # type: ignore

        if result:
            await interaction.followup.send(f"{settings.collectible_name.title()} dropped.", ephemeral=True)
            log.info(f"{interaction.user} dropped {countryball} (`{countryball.pk:0X}`) in {interaction.channel}.")
        else:
            await countryball.unlock()
            await interaction.followup.send(
                f"Failed to drop the {settings.collectible_name}, please try again later.", ephemeral=True
            )

    @app_commands.command(extras={"trade": TradeCommandType.PICK})
    async def give(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Give a countryball to a user.

        Parameters
        ----------
        user: discord.User
            The user you want to give a countryball to
        countryball: BallInstance
            The countryball you're giving away
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        """
        if not countryball:
            return
        skip_reason = await check_giveable(countryball)
        if skip_reason == GiveSkipReason.NOT_TRADEABLE:
            await interaction.response.send_message(
                f"You cannot donate this {settings.collectible_name}.", ephemeral=True
            )
            return
        if user.bot:
            await interaction.response.send_message("You cannot donate to bots.", ephemeral=True)
            return
        if skip_reason == GiveSkipReason.LOCKED:
            await interaction.response.send_message(
                f"This {settings.collectible_name} is currently locked for a trade. Please try again later.",
                ephemeral=True,
            )
            return
        favorite = countryball.favorite
        if favorite:
            view = ConfirmChoiceView(
                interaction,
                accept_message=f"{settings.collectible_name.title()} donated.",
                cancel_message="This request has been cancelled.",
            )
            await interaction.response.send_message(
                f"This {settings.collectible_name} is a favorite, are you sure you want to donate it?",
                view=view,
                ephemeral=True,
            )
            await view.wait()
            if not view.value:
                return
            interaction = view.interaction_response
        else:
            await interaction.response.defer()
        await countryball.lock_for_trade()
        new_player, _ = await Player.objects.aget_or_create(discord_id=user.id)
        old_player = countryball.player

        error = await check_recipient(self.bot, new_player, old_player)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            await countryball.unlock()
            return
        if new_player.donation_policy == DonationPolicy.REQUEST_APPROVAL:
            await interaction.followup.send(
                f"Hey {user.mention}, {interaction.user.name} wants to give you "
                f"{countryball.description(include_emoji=True, bot=self.bot, is_trade=True)}!\n"
                "Do you accept this donation?",
                view=DonationRequest(self.bot, interaction, countryball, new_player),
                allowed_mentions=await can_mention([new_player, old_player]),
            )
            return

        countryball.player = new_player
        countryball.trade_player = old_player
        countryball.favorite = False
        await countryball.asave()

        trade = await Trade.objects.acreate(player1=old_player, player2=new_player)
        await TradeObject.objects.acreate(trade=trade, ballinstance=countryball, player=old_player)

        cb_txt = (
            countryball.description(short=True, include_emoji=True, bot=self.bot, is_trade=True)
            + f" (`{countryball.attack_bonus:+}%/{countryball.health_bonus:+}%`)"
        )
        if favorite:
            await interaction.followup.send(
                f"{interaction.user.mention}, you just gave the "
                f"{settings.collectible_name} {cb_txt} to {user.mention}!",
                allowed_mentions=await can_mention([new_player, old_player]),
            )
        else:
            await interaction.followup.send(
                f"You just gave the {settings.collectible_name} {cb_txt} to {user.mention}!",
                allowed_mentions=await can_mention([new_player]),
            )
        await countryball.unlock()

    @app_commands.command()
    async def bulk_give(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
        countryball: BallEnabledTransform | None = None,
        sort: SortingChoices | None = None,
        special: SpecialEnabledTransform | None = None,
        filter: FilteringChoices | None = None,
    ):
        """
        Give multiple countryballs to a user at once.

        Parameters
        ----------
        user: discord.User
            The user you want to give countryballs to
        countryball: Ball
            Filter the selection to a specific countryball
        sort: SortingChoices
            Choose how countryballs are sorted. Can be used to show duplicates.
        special: Special
            Filter the selection to a specific special event
        filter: FilteringChoices
            Filter the selection by a specific filter
        """
        if user.bot:
            await interaction.response.send_message("You cannot donate to bots.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        old_player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        new_player, _ = await Player.objects.aget_or_create(discord_id=user.id)

        error = await check_recipient(self.bot, new_player, old_player)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        query = (
            BallInstance.objects.filter(
                Q(locked=None) | Q(locked__lt=timezone.now() - timedelta(seconds=60)),
                player__discord_id=interaction.user.id,
            )
            .exclude(tradeable=False)
            .exclude(ball__tradeable=False)
            .exclude(special__tradeable=False)
        )
        if countryball:
            query = query.filter(ball=countryball)
        if special:
            query = query.filter(special=special)
        if sort:
            query = sort_balls(sort, query)
        if filter:
            query = filter_balls(filter, query, interaction.guild_id)
        query.query.add_ordering("-id")  # enforce a unique ordering to prevent mismatch during pagination
        if not await query.aexists():
            await interaction.followup.send(f"No {settings.plural_collectible_name} found.", ephemeral=True)
            return

        view = TrackedLayoutView()
        selector = BulkGiveSelector()
        view.add_item(selector)
        await selector.configure(self.bot, query, user=user, new_player=new_player, old_player=old_player)
        message = await interaction.followup.send(view=view, ephemeral=True, wait=True)
        view.original_message = message

    @app_commands.command()
    async def count(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallEnabledTransform | None = None,
        special: SpecialEnabledTransform | None = None,
        filter: FilteringChoices | None = None,
    ):
        """
        Count how many countryballs you have.

        Parameters
        ----------
        countryball: Ball
            The countryball you want to count
        special: Special
            The special you want to count
        filter: FilteringChoices
            Filter the count by a specific filter
        """
        if interaction.response.is_done():
            return

        guild = interaction.guild
        filters = {}
        if countryball:
            filters["ball"] = countryball
        if special:
            filters["special"] = special
        filters["player__discord_id"] = interaction.user.id

        await interaction.response.defer(ephemeral=True, thinking=True)

        query = BallInstance.objects.filter(**filters)
        if filter:
            query = filter_balls(filter, query, interaction.guild_id)
        balls = await query.acount()
        country = f"{countryball.country} " if countryball else ""
        plural = "s" if balls > 1 or balls == 0 else ""
        special_str = f"{special.name} " if special else ""
        guild_text = f" caught in {guild.name}" if filter == FilteringChoices.this_server and guild else ""

        await interaction.followup.send(
            f"You have {balls:,} {special_str}{country}{settings.collectible_name}{plural}{guild_text}."
        )

    @app_commands.command()
    @app_commands.checks.cooldown(1, 20, key=lambda i: i.user.id)
    async def duplicate(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        type: DuplicateType,
        sort: DuplicateSort | None = None,
        limit: app_commands.Range[int, 1] | None = None,
        reverse: bool = False,
    ):
        """
        Shows your most duplicated countryballs or specials.

        Parameters
        ----------
        type: DuplicateType
            Type of duplicate to check (countryballs or specials).
        sort: DuplicateSort
            Choose how the results are sorted. Defaults to most duplicated first.
        limit: int | None
            The amount of countryballs to show (default: all), can only be used with `countryballs`.
        reverse: bool
            Show your least duplicated countryballs or specials first instead.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)

        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        is_special = type == DuplicateType.specials
        queryset = BallInstance.objects.filter(player=player)

        if is_special:
            queryset = queryset.filter(special_id__isnull=False).prefetch_related("special")
            annotations = {
                "name": F("special__name"),
                "emoji": F("special__emoji"),
                "value_id": F("special_id"),
                "rarity": F("special__rarity"),
            }
            apply_limit = False
        else:
            queryset = queryset.filter(ball__tradeable=True)
            annotations = {
                "name": F("ball__country"),
                "emoji": F("ball__emoji_id"),
                "value_id": F("ball_id"),
                "rarity": F("ball__rarity"),
            }
            apply_limit = True

        query = (
            queryset.values(annotations["value_id"].name)
            .annotate(**annotations, count=Count("value_id"))
            .order_by(sort.value if sort else DuplicateSort.count_desc.value)
        )

        if apply_limit and limit is not None:
            query = query[:limit]

        if not await query.aexists():
            await interaction.followup.send(
                f"You don't have any {type.value} duplicates in your inventory.", ephemeral=True
            )
            return

        entries = [
            discord.SelectOption(
                label=item["name"],
                emoji=item["emoji"] if is_special else self.bot.get_emoji(item["emoji"]),
                description=f"Count: {item['count']}",
                value=item["value_id"],
            )
            async for item in query
        ]

        view = CountryballsDuplicateSource(is_special)
        view.restrict_author(interaction.user.id)
        order_msg = " (least duplicated first)" if reverse else ""
        view.header.content = f"View your duplicate {type.value}{order_msg}."
        menu = Menu(self.bot, view, ChunkedListSource(entries), SelectFormatter(view.callback))
        await menu.init()
        await interaction.followup.send(view=view)

    @app_commands.command()
    @app_commands.checks.cooldown(1, 20, key=lambda i: i.user.id)
    async def compare(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
        special: SpecialEnabledTransform | None = None,
        duplicates: bool = False,
        filter: FilteringChoices | None = None,
        diff_only: bool = False,
    ):
        """
        Compare your countryballs with another user.

        Parameters
        ----------
        user: discord.User
            The user you want to compare with
        special: Special
            Filter the results of the comparison to a special event.
        duplicates: bool
            Whether to compare duplicates.
        filter: FilteringChoices
            Filter the compared countryballs by a specific filter.
        diff_only: bool
            Only show what's different between you and the other user, hiding "Both have" and
            "Neither have" - useful for large collections.
        """
        await interaction.response.defer(thinking=True)
        if interaction.user == user:
            await interaction.followup.send("You cannot compare with yourself.", ephemeral=True)
            return

        try:
            player = await Player.objects.aget(discord_id=user.id)
        except Player.DoesNotExist:
            await interaction.followup.send(
                f"{user.display_name} doesn't have any {settings.plural_collectible_name} yet."
            )
            return

        staff = await is_staff(interaction)
        if user.id in self.bot.blacklist and not staff:
            await interaction.followup.send("You cannot compare the inventory of a blacklisted user.", ephemeral=True)
            return

        if await inventory_privacy(self.bot, interaction, player, user) is False:
            return

        bot_countryballs = {x: y.emoji_id for x, y in balls.items() if y.enabled}
        if special:
            bot_countryballs = {
                x: y.emoji_id
                for x, y in balls.items()
                if y.enabled and (special.end_date is None or y.created_at is None or y.created_at < special.end_date)
            }

        player1, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        player2, _ = await Player.objects.aget_or_create(discord_id=user.id)

        blocked = await player.is_blocked(player1)
        if blocked and not staff:
            await interaction.followup.send("You cannot compare with a user that has you blocked.", ephemeral=True)
            return

        blocked = await player.is_blocked(player2)
        if blocked and not staff:
            await interaction.followup.send("You cannot compare with a user that has you blocked.", ephemeral=True)
            return
        queryset = BallInstance.objects.filter(ball__enabled=True).distinct()
        if special:
            queryset = queryset.filter(special=special)
        if filter:
            queryset = filter_balls(filter, queryset, interaction.guild_id)
        if duplicates:
            queryset = queryset.values("ball_id").annotate(counts=Count("ball_id")).filter(counts__gt=1)
        user1_balls = cast(
            list[int], [x async for x in queryset.filter(player=player1).values_list("ball_id", flat=True)]
        )
        user2_balls = cast(
            list[int], [x async for x in queryset.filter(player=player2).values_list("ball_id", flat=True)]
        )

        special_str = f" ({special.name})" if special else ""
        comparison_type = "Duplicates Comparison" if duplicates else "Comparison"
        text = (
            f"## {comparison_type} of {interaction.user.display_name} and {user.display_name}'s "
            f"{settings.plural_collectible_name}{special_str}\n"
        )

        def fill_fields(title: str, ids: set[int]):
            nonlocal text
            text += f"### {title}{' duplicates' if duplicates else ''}\n"
            if not ids:
                text += "None\n"
                return

            # deterministic, readable ordering instead of arbitrary set iteration order
            for ball_id in sorted(ids, key=lambda i: balls[i].country if i in balls else ""):
                emoji = self.bot.get_emoji(bot_countryballs[ball_id])
                if not emoji:
                    continue
                text += f"{emoji} "
            text += "\n"

        all_ball_ids = set(bot_countryballs.keys())
        u1_s, u2_s = set(user1_balls), set(user2_balls)
        if not diff_only:
            fill_fields("Both have", u1_s & u2_s)
        fill_fields(f"Only {interaction.user.display_name} has", u1_s - u2_s)
        fill_fields(f"Only {user.display_name} has", u2_s - u1_s)
        if not diff_only:
            fill_fields("Neither have", all_ball_ids - u1_s - u2_s)

        view = LayoutView()
        container = Container()
        display = TextDisplay("")
        container.add_item(display)
        view.add_item(container)
        menu = Menu(self.bot, view, TextSource(text, delims=["\n###", " "]), TextFormatter(display))
        await menu.init()
        await interaction.followup.send(view=view)

    @app_commands.command()
    async def collection(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallEnabledTransform | None = None,
        ephemeral: bool = False,
    ):
        """
        Show the collection of a specific countryball.

        Parameters
        ----------
        countryball: Ball
            The countryball you want to see the collection of
        ephemeral: bool
            Whether or not to send the command ephemerally.
        """
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)

        query = (
            BallInstance.objects.filter(player=player)
            .values("player_id")
            .annotate(
                total=Count("id"),
                traded=Count("id", filter=Q(trade_player_id__isnull=False)),
                specials=Count(
                    "id",
                    filter=Q(special_id__isnull=False)
                    & ~Exists(Special.objects.filter(hidden=True, id=OuterRef("special_id"))),
                ),
            )
        )
        specials = (
            BallInstance.objects.filter(player=player)
            .exclude(special=None)
            .exclude(special__hidden=True)
            .values("special__name")
            .annotate(count=Count("special__name"))
            .order_by("-count")
        )
        if countryball:
            query = query.filter(ball=countryball)
            specials = specials.filter(ball=countryball)

        try:
            counts = await query.aget()
        except BallInstance.DoesNotExist:
            if countryball:
                await interaction.followup.send(
                    f"You don't have any {countryball.country} {settings.plural_collectible_name} yet."
                )
            else:
                await interaction.followup.send(f"You don't have any {settings.plural_collectible_name} yet.")
            return
        all_specials = Special.objects.filter(hidden=False)
        special_emojis = {x.name: x.emoji async for x in all_specials}

        desc = (
            f"**Total**: {counts['total']:,} ({counts['total'] - counts['traded']:,} caught, "
            f"{counts['traded']:,} received from trade)\n"
            f"**Total Specials**: {counts['specials']:,}\n\n"
        )
        if counts["specials"]:
            desc += "**Specials**:\n"
        async for special in specials:
            emoji = special_emojis.get(special["special__name"], "")
            desc += f"{emoji} {special['special__name']}: {special['count']:,}\n"

        embed = discord.Embed(
            title=f"Collection of {countryball.country}" if countryball else "Total Collection",
            description=desc,
            color=discord.Color.blurple(),
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        if countryball:
            file_location = countryball.wild_card.path
            file = discord.File(file_location, filename="countryball.png")
            embed.set_thumbnail(url="attachment://countryball.png")
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed)
