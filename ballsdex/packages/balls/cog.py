import enum
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, button
from tortoise.exceptions import DoesNotExist
from tortoise.functions import Count

from ballsdex.core.models import BallInstance, DonationPolicy, Player, Trade, TradeObject, balls
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.core.utils.sorting import SortingChoices, sort_balls
from ballsdex.core.utils.transformers import (
    BallEnabledTransform,
    BallInstanceTransform,
    SpecialEnabledTransform,
    TradeCommandType,
)
from ballsdex.core.utils.utils import inventory_privacy, is_staff
from ballsdex.packages.balls.countryballs_paginator import CountryballsViewer
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.countryballs")


class DonationRequest(View):
    def __init__(
        self,
        bot: "BallsDexBot",
        interaction: discord.Interaction,
        countryball: BallInstance,
        new_player: Player,
    ):
        super().__init__(timeout=120)
        self.bot = bot
        self.original_interaction = interaction
        self.countryball = countryball
        self.new_player = new_player

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if interaction.user.id != self.new_player.discord_id:
            await interaction.response.send_message(
                "You are not allowed to interact with this menu.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True  # type: ignore
        try:
            await self.original_interaction.followup.edit_message(
                "@original", view=self  # type: ignore
            )
        except discord.NotFound:
            pass
        await self.countryball.unlock()

    @button(
        style=discord.ButtonStyle.success, emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}"
    )
    async def accept(self, interaction: discord.Interaction, button: Button):
        self.stop()
        for item in self.children:
            item.disabled = True  # type: ignore
        self.countryball.favorite = False
        self.countryball.trade_player = self.countryball.player
        self.countryball.player = self.new_player
        await self.countryball.save()
        trade = await Trade.create(player1=self.countryball.trade_player, player2=self.new_player)
        await TradeObject.create(
            trade=trade, ballinstance=self.countryball, player=self.countryball.trade_player
        )
        await interaction.response.edit_message(
            content=interaction.message.content  # type: ignore
            + "\n\N{WHITE HEAVY CHECK MARK} The donation was accepted!",
            view=self,
        )
        await self.countryball.unlock()

    @button(
        style=discord.ButtonStyle.danger,
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
    )
    async def deny(self, interaction: discord.Interaction, button: Button):
        self.stop()
        for item in self.children:
            item.disabled = True  # type: ignore
        await interaction.response.edit_message(
            content=interaction.message.content  # type: ignore
            + "\n\N{CROSS MARK} The donation was denied.",
            view=self,
        )
        await self.countryball.unlock()


class DuplicateType(enum.Enum):
    countryballs = "countryballs"
    specials = "specials"


class Balls(commands.GroupCog, group_name=settings.players_group_cog_name):
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
        special: SpecialEnabledTransform | None = None,
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
        special: Special
            Filter the list by a specific special event.
        """
        user_obj = user or interaction.user
        await interaction.response.defer(thinking=True)

        try:
            player = await Player.get(discord_id=user_obj.id)
        except DoesNotExist:
            if user_obj == interaction.user:
                await interaction.followup.send(
                    f"You don't have any {settings.plural_collectible_name} yet."
                )
            else:
                await interaction.followup.send(
                    f"{user_obj.name} doesn't have any {settings.plural_collectible_name} yet."
                )
            return
        if user is not None:
            if await inventory_privacy(self.bot, interaction, player, user_obj) is False:
                return

        interaction_player, _ = await Player.get_or_create(discord_id=interaction.user.id)

        blocked = await player.is_blocked(interaction_player)
        if blocked and not is_staff(interaction):
            await interaction.followup.send(
                "You cannot view the list of a user that has you blocked.", ephemeral=True
            )
            return

        await player.fetch_related("balls")
        query = player.balls.all()
        if countryball:
            query = query.filter(ball__id=countryball.pk)
        if special:
            query = query.filter(special=special)
        if sort:
            countryballs = await sort_balls(sort, query)
        else:
            countryballs = await query.order_by("-favorite")

        if len(countryballs) < 1:
            ball_txt = countryball.country if countryball else ""
            special_txt = special if special else ""

            if special_txt and ball_txt:
                combined = f"{special_txt} {ball_txt}"
            elif special_txt:
                combined = special_txt
            elif ball_txt:
                combined = ball_txt
            else:
                combined = ""

            if user_obj == interaction.user:
                await interaction.followup.send(
                    f"You don't have any {combined} {settings.plural_collectible_name} yet."
                )
            else:
                await interaction.followup.send(
                    f"{user_obj.name} doesn't have any {combined} "
                    f"{settings.plural_collectible_name} yet."
                )
            return
        if reverse:
            countryballs.reverse()

        paginator = CountryballsViewer(interaction, countryballs)
        if user_obj == interaction.user:
            await paginator.start()
        else:
            await paginator.start(
                content=f"Viewing {user_obj.name}'s {settings.plural_collectible_name}"
            )

    @app_commands.command()
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def completion(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User | None = None,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Show your current completion of the BallsDex.

        Parameters
        ----------
        user: discord.User
            The user whose completion you want to view, if not yours.
        special: Special
            The special you want to see the completion of
        """
        user_obj = user or interaction.user
        await interaction.response.defer(thinking=True)
        extra_text = f"{special.name} " if special else ""
        if user is not None:
            try:
                player = await Player.get(discord_id=user_obj.id)
            except DoesNotExist:
                await interaction.followup.send(
                    f"{user_obj.name} doesn't have any "
                    f"{extra_text}{settings.plural_collectible_name} yet."
                )
                return

            interaction_player, _ = await Player.get_or_create(discord_id=interaction.user.id)

            blocked = await player.is_blocked(interaction_player)
            if blocked and not is_staff(interaction):
                await interaction.followup.send(
                    "You cannot view the completion of a user that has blocked you.",
                    ephemeral=True,
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
                if y.enabled and (special.end_date is None or y.created_at < special.end_date)
            }
        if not bot_countryballs:
            await interaction.followup.send(
                f"There are no {extra_text}{settings.plural_collectible_name}"
                " registered on this bot yet.",
                ephemeral=True,
            )
            return

        owned_countryballs = set(
            x[0]
            for x in await BallInstance.filter(**filters)
            .distinct()  # Do not query everything
            .values_list("ball_id")
        )

        entries: list[tuple[str, str]] = []

        def fill_fields(title: str, emoji_ids: set[int]):
            # check if we need to add "(continued)" to the field name
            first_field_added = False
            buffer = ""

            for emoji_id in emoji_ids:
                emoji = self.bot.get_emoji(emoji_id)
                if not emoji:
                    continue

                text = f"{emoji} "
                if len(buffer) + len(text) > 1024:
                    # hitting embed limits, adding an intermediate field
                    if first_field_added:
                        entries.append(("\u200B", buffer))
                    else:
                        entries.append((f"__**{title}**__", buffer))
                        first_field_added = True
                    buffer = ""
                buffer += text

            if buffer:  # add what's remaining
                if first_field_added:
                    entries.append(("\u200B", buffer))
                else:
                    entries.append((f"__**{title}**__", buffer))

        if owned_countryballs:
            # Getting the list of emoji IDs from the IDs of the owned countryballs
            fill_fields(
                f"Owned {settings.plural_collectible_name}",
                set(bot_countryballs[x] for x in owned_countryballs),
            )
        else:
            entries.append((f"__**Owned {settings.plural_collectible_name}**__", "Nothing yet."))

        if missing := set(y for x, y in bot_countryballs.items() if x not in owned_countryballs):
            fill_fields(f"Missing {settings.plural_collectible_name}", missing)
        else:
            entries.append(
                (
                    f"__**:tada: No missing {settings.plural_collectible_name}, "
                    "congratulations! :tada:**__",
                    "\u200B",
                )
            )  # force empty field value

        source = FieldPageSource(entries, per_page=5, inline=False, clear_description=False)
        special_str = f" ({special.name})" if special else ""
        source.embed.description = (
            f"{settings.bot_name}{special_str} progression: "
            f"**{round(len(owned_countryballs) / len(bot_countryballs) * 100, 1)}%**"
        )
        source.embed.colour = discord.Colour.blurple()
        source.embed.set_author(name=user_obj.display_name, icon_url=user_obj.display_avatar.url)

        pages = Pages(source=source, interaction=interaction, compact=True)
        await pages.start()

    @app_commands.command()
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def info(
        self,
        interaction: discord.Interaction,
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Display info from a specific countryball.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to inspect
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        """
        if not countryball:
            return
        await interaction.response.defer(thinking=True)
        content, file = await countryball.prepare_for_message(interaction)
        await interaction.followup.send(content=content, file=file)
        file.close()

    @app_commands.command()
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def last(self, interaction: discord.Interaction, user: discord.User | None = None):
        """
        Display info of your or another users last caught countryball.

        Parameters
        ----------
        user: discord.Member
            The user you would like to see
        """
        user_obj = user if user else interaction.user
        await interaction.response.defer(thinking=True)
        try:
            player = await Player.get(discord_id=user_obj.id)
        except DoesNotExist:
            msg = f"{'You do' if user is None else f'{user_obj.display_name} does'}"
            await interaction.followup.send(
                f"{msg} not have any {settings.plural_collectible_name} yet.",
                ephemeral=True,
            )
            return

        if user is not None:
            if await inventory_privacy(self.bot, interaction, player, user_obj) is False:
                return

        interaction_player, _ = await Player.get_or_create(discord_id=interaction.user.id)

        blocked = await player.is_blocked(interaction_player)
        if blocked and not is_staff(interaction):
            await interaction.followup.send(
                f"You cannot view the last caught {settings.collectible_name} "
                "of a user that has blocked you.",
                ephemeral=True,
            )
            return

        countryball = await player.balls.all().order_by("-id").first().select_related("ball")
        if not countryball:
            msg = f"{'You do' if user is None else f'{user_obj.display_name} does'}"
            await interaction.followup.send(
                f"{msg} not have any {settings.plural_collectible_name} yet.",
                ephemeral=True,
            )
            return

        content, file = await countryball.prepare_for_message(interaction)
        if user is not None and user.id != interaction.user.id:
            content = (
                f"You are viewing {user.display_name}'s last caught {settings.collectible_name}.\n"
                + content
            )
        await interaction.followup.send(content=content, file=file)
        file.close()

    @app_commands.command()
    async def favorite(
        self,
        interaction: discord.Interaction,
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
                player = await Player.get(discord_id=interaction.user.id).prefetch_related("balls")
            except DoesNotExist:
                await interaction.response.send_message(
                    f"You don't have any {settings.plural_collectible_name} yet.", ephemeral=True
                )
                return

            grammar = (
                f"{settings.collectible_name}"
                if settings.max_favorites == 1
                else f"{settings.plural_collectible_name}"
            )
            if await player.balls.filter(favorite=True).count() >= settings.max_favorites:
                await interaction.response.send_message(
                    f"You cannot set more than {settings.max_favorites} favorite {grammar}.",
                    ephemeral=True,
                )
                return

            countryball.favorite = True  # type: ignore
            await countryball.save()
            emoji = self.bot.get_emoji(countryball.countryball.emoji_id) or ""
            await interaction.response.send_message(
                f"{emoji} `#{countryball.pk:0X}` {countryball.countryball.country} "
                f"is now a favorite {settings.collectible_name}!",
                ephemeral=True,
            )

        else:
            countryball.favorite = False  # type: ignore
            await countryball.save()
            emoji = self.bot.get_emoji(countryball.countryball.emoji_id) or ""
            await interaction.response.send_message(
                f"{emoji} `#{countryball.pk:0X}` {countryball.countryball.country} "
                f"isn't a favorite {settings.collectible_name} anymore.",
                ephemeral=True,
            )

    @app_commands.command(extras={"trade": TradeCommandType.PICK})
    async def give(
        self,
        interaction: discord.Interaction,
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
        if not countryball.is_tradeable:
            await interaction.response.send_message(
                f"You cannot donate this {settings.collectible_name}.", ephemeral=True
            )
            return
        if user.bot:
            await interaction.response.send_message("You cannot donate to bots.", ephemeral=True)
            return
        if await countryball.is_locked():
            await interaction.response.send_message(
                f"This {settings.collectible_name} is currently locked for a trade. "
                "Please try again later.",
                ephemeral=True,
            )
            return
        if countryball.favorite:
            view = ConfirmChoiceView(
                interaction,
                accept_message=f"{settings.collectible_name.title()} donated.",
                cancel_message="This request has been cancelled.",
            )
            await interaction.response.send_message(
                f"This {settings.collectible_name} is a favorite, "
                "are you sure you want to donate it?",
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
        new_player, _ = await Player.get_or_create(discord_id=user.id)
        old_player = countryball.player

        if new_player == old_player:
            await interaction.followup.send(
                f"You cannot give a {settings.collectible_name} to yourself.", ephemeral=True
            )
            await countryball.unlock()
            return
        if new_player.donation_policy == DonationPolicy.ALWAYS_DENY:
            await interaction.followup.send(
                "This player does not accept donations. You can use trades instead.",
                ephemeral=True,
            )
            await countryball.unlock()
            return

        friendship = await new_player.is_friend(old_player)
        if new_player.donation_policy == DonationPolicy.FRIENDS_ONLY:
            if not friendship:
                await interaction.followup.send(
                    "This player only accepts donations from friends, use trades instead.",
                    ephemeral=True,
                )
                await countryball.unlock()
                return
        blocked = await new_player.is_blocked(old_player)
        if blocked:
            await interaction.followup.send(
                "You cannot interact with a user that has blocked you.", ephemeral=True
            )
            await countryball.unlock()
            return
        if new_player.discord_id in self.bot.blacklist:
            await interaction.followup.send(
                "You cannot donate to a blacklisted user.", ephemeral=True
            )
            await countryball.unlock()
            return
        elif new_player.donation_policy == DonationPolicy.REQUEST_APPROVAL:
            await interaction.followup.send(
                f"Hey {user.mention}, {interaction.user.name} wants to give you "
                f"{countryball.description(include_emoji=True, bot=self.bot, is_trade=True)}!\n"
                "Do you accept this donation?",
                view=DonationRequest(self.bot, interaction, countryball, new_player),
                allowed_mentions=discord.AllowedMentions(users=new_player.can_be_mentioned),
            )
            return

        countryball.player = new_player
        countryball.trade_player = old_player
        countryball.favorite = False
        await countryball.save()

        trade = await Trade.create(player1=old_player, player2=new_player)
        await TradeObject.create(trade=trade, ballinstance=countryball, player=old_player)

        cb_txt = (
            countryball.description(short=True, include_emoji=True, bot=self.bot, is_trade=True)
            + f" (`{countryball.attack_bonus:+}%/{countryball.health_bonus:+}%`)"
        )
        await interaction.followup.send(
            f"You just gave the {settings.collectible_name} {cb_txt} to {user.mention}!",
            allowed_mentions=discord.AllowedMentions(users=new_player.can_be_mentioned),
        )
        await countryball.unlock()

    @app_commands.command()
    async def count(
        self,
        interaction: discord.Interaction,
        countryball: BallEnabledTransform | None = None,
        special: SpecialEnabledTransform | None = None,
        current_server: bool = False,
    ):
        """
        Count how many countryballs you have.

        Parameters
        ----------
        countryball: Ball
            The countryball you want to count
        special: Special
            The special you want to count
        current_server: bool
            Only count countryballs caught in the current server
        """
        if interaction.response.is_done():
            return
        assert interaction.guild
        filters = {}
        if countryball:
            filters["ball"] = countryball
        if special:
            filters["special"] = special
        if current_server:
            filters["server_id"] = interaction.guild.id
        filters["player__discord_id"] = interaction.user.id
        await interaction.response.defer(ephemeral=True, thinking=True)
        balls = await BallInstance.filter(**filters).count()
        country = f"{countryball.country} " if countryball else ""
        plural = "s" if balls > 1 or balls == 0 else ""
        special_str = f"{special.name} " if special else ""
        guild = f" caught in {interaction.guild.name}" if current_server else ""
        await interaction.followup.send(
            f"You have {balls} {special_str}"
            f"{country}{settings.collectible_name}{plural}{guild}."
        )

    @app_commands.command()
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def duplicate(
        self, interaction: discord.Interaction["BallsDexBot"], type: DuplicateType
    ):
        """
        Shows your most duplicated countryballs or specials.

        Parameters
        ----------
        type: DuplicateType
            Type of duplicate to check (countryballs or specials).
        """
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        player, _ = await Player.get_or_create(discord_id=user_id)
        await player.fetch_related("balls")
        is_special = type.value == "specials"
        queryset = BallInstance.filter(player=player)

        if type.value == "specials":
            queryset = queryset.filter(special_id__isnull=False).prefetch_related("special")
            annotations = {
                "name": "special__name",
                "emoji": "special__emoji",
            }
            limit = 5
            title = "specials"
        else:
            queryset = queryset.filter(ball__tradeable=True)
            annotations = {
                "name": "ball__country",
                "emoji": "ball__emoji_id",
            }
            limit = 50
            title = settings.plural_collectible_name

        queryset = (
            queryset.annotate(count=Count("id"))
            .group_by(*annotations.values())
            .order_by("-count")
            .limit(limit)
            .values(*annotations.values(), "count")
        )
        results = await queryset

        if not results:
            await interaction.followup.send(
                f"You don't have any {type.value} duplicates in your inventory!",
                ephemeral=True,
            )
            return

        entries = [
            (
                f"{i + 1}. {item[annotations['name']]} "
                f"{self.bot.get_emoji(item[annotations['emoji']]) or item[annotations['emoji']]}",
                f"Count: {item['count']}",
            )
            for i, item in enumerate(results)
        ]
        source = FieldPageSource(entries, per_page=5 if is_special else 10, inline=False)
        source.embed.title = f"Top {len(results)} duplicate {title}"
        source.embed.color = discord.Color.purple() if is_special else discord.Color.blue()
        source.embed.set_thumbnail(url=interaction.user.display_avatar.url)
        paginator = Pages(source, interaction=interaction)
        await paginator.start(ephemeral=True)
