import enum
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Union

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, button
from tortoise.exceptions import DoesNotExist

from ballsdex.core.models import (
    BallInstance,
    DonationPolicy,
    Player,
    PrivacyPolicy,
    Trade,
    TradeObject,
    balls,
)
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.core.utils.transformers import (
    BallEnabledTransform,
    BallInstanceTransform,
    SpecialEnabledTransform,
    TradeCommandType,
)
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


class SortingChoices(enum.Enum):
    alphabetic = "ball__country"
    catch_date = "-catch_date"
    rarity = "ball__rarity"
    special = "special__id"
    health = "health"
    attack = "attack"
    health_bonus = "-health_bonus"
    attack_bonus = "-attack_bonus"
    stats_bonus = "stats"
    total_stats = "total_stats"

    # manual sorts are not sorted by SQL queries but by our code
    # this may be do-able with SQL still, but I don't have much experience ngl
    duplicates = "manualsort-duplicates"


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
        interaction_player = await Player.get(discord_id=interaction.user.id)

        blocked = await player.is_blocked(interaction_player)
        if blocked:
            await interaction.followup.send(
                "You cannot view the list of a user that has you blocked.", ephemeral=True
            )
            return

        await player.fetch_related("balls")
        filters = {"ball__id": countryball.pk} if countryball else {}
        if special:
            filters["special"] = special
        if sort:
            if sort == SortingChoices.duplicates:
                countryballs = await player.balls.filter(**filters)
                count = defaultdict(int)
                for ball in countryballs:
                    count[ball.countryball.pk] += 1
                countryballs.sort(key=lambda m: (-count[m.countryball.pk], m.countryball.pk))
            elif sort == SortingChoices.stats_bonus:
                countryballs = await player.balls.filter(**filters)
                countryballs.sort(key=lambda x: x.health_bonus + x.attack_bonus, reverse=True)
            elif sort == SortingChoices.health or sort == SortingChoices.attack:
                countryballs = await player.balls.filter(**filters)
                countryballs.sort(key=lambda x: getattr(x, sort.value), reverse=True)
            elif sort == SortingChoices.total_stats:
                countryballs = await player.balls.filter(**filters)
                countryballs.sort(key=lambda x: x.health + x.attack, reverse=True)
            elif sort == SortingChoices.rarity:
                countryballs = await player.balls.filter(**filters).order_by(
                    sort.value, "ball__country"
                )
            else:
                countryballs = await player.balls.filter(**filters).order_by(sort.value)
        else:
            countryballs = await player.balls.filter(**filters).order_by("-favorite", "-shiny")

        if len(countryballs) < 1:
            ball_txt = countryball.country if countryball else ""
            special_txt = special if special else ""
            if user_obj == interaction.user:
                await interaction.followup.send(
                    f"You don't have any {special_txt}{ball_txt} "
                    f"{settings.plural_collectible_name} yet."
                )
            else:
                await interaction.followup.send(
                    f"{user_obj.name} doesn't have any "
                    f"{special_txt}{ball_txt} {settings.plural_collectible_name} yet."
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
        shiny: bool | None = None,
    ):
        """
        Show your current completion of the BallsDex.

        Parameters
        ----------
        user: discord.User
            The user whose completion you want to view, if not yours.
        special: Special
            The special you want to see the completion of
        shiny: bool
            Whether you want to see the completion of shiny countryballs
        """
        user_obj = user or interaction.user
        await interaction.response.defer(thinking=True)
        extra_text = "shiny " if shiny else "" + f"{special.name} " if special else ""
        if user is not None:
            try:
                player = await Player.get(discord_id=user_obj.id)
            except DoesNotExist:
                await interaction.followup.send(
                    f"{user_obj.name} doesn't have any "
                    f"{extra_text}{settings.plural_collectible_name} yet."
                )
                return

            interaction_player = await Player.get(discord_id=interaction.user.id)
            blocked = await player.is_blocked(interaction_player)
            if blocked:
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
                if y.enabled and y.created_at < special.end_date
            }
        if not bot_countryballs:
            await interaction.followup.send(
                f"There are no {extra_text}{settings.plural_collectible_name}"
                " registered on this bot yet.",
                ephemeral=True,
            )
            return

        if shiny is not None:
            filters["shiny"] = shiny
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
        shiny_str = " shiny" if shiny else ""
        source.embed.description = (
            f"{settings.bot_name}{special_str}{shiny_str} progression: "
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
        shiny: bool | None = None,
    ):
        """
        Display info from a specific countryball.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to inspect
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        shiny: bool
            Filter the results of autocompletion to shinies. Ignored afterwards.
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

        interaction_player = await Player.get(discord_id=interaction.user.id)
        blocked = await player.is_blocked(interaction_player)
        if blocked:
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
        shiny: bool | None = None,
    ):
        """
        Set favorite countryballs.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to set/unset as favorite
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        shiny: bool
            Filter the results of autocompletion to shinies. Ignored afterwards.
        """
        if not countryball:
            return

        if settings.max_favorites == 0:
            await interaction.response.send_message(
                f"You cannot set favorite {settings.plural_collectible_name} in this bot."
            )
            return

        if not countryball.favorite:
            player = await Player.get(discord_id=interaction.user.id).prefetch_related("balls")
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
        shiny: bool | None = None,
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
        shiny: bool
            Filter the results of autocompletion to shinies. Ignored afterwards.
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
            view = ConfirmChoiceView(interaction)
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
        shiny: bool | None = None,
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
        shiny: bool
            Whether you want to count shiny countryballs
        current_server: bool
            Only count countryballs caught in the current server
        """
        if interaction.response.is_done():
            return
        assert interaction.guild
        filters = {}
        if countryball:
            filters["ball"] = countryball
        if shiny is not None:
            filters["shiny"] = shiny
        if special:
            filters["special"] = special
        if current_server:
            filters["server_id"] = interaction.guild.id
        filters["player__discord_id"] = interaction.user.id
        await interaction.response.defer(ephemeral=True, thinking=True)
        balls = await BallInstance.filter(**filters).count()
        country = f"{countryball.country} " if countryball else ""
        plural = "s" if balls > 1 or balls == 0 else ""
        shiny_str = "shiny " if shiny else ""
        special_str = f"{special.name} " if special else ""
        guild = f" caught in {interaction.guild.name}" if current_server else ""
        await interaction.followup.send(
            f"You have {balls} {special_str}{shiny_str}"
            f"{country}{settings.collectible_name}{plural}{guild}."
        )


async def inventory_privacy(
    bot: "BallsDexBot",
    interaction: discord.Interaction,
    player: Player,
    user_obj: Union[discord.User, discord.Member],
):
    privacy_policy = player.privacy_policy
    interacting_player = await Player.get(discord_id=interaction.user.id)
    if interaction.user.id == player.discord_id:
        return True
    if interaction.guild and interaction.guild.id in settings.admin_guild_ids:
        roles = settings.admin_role_ids + settings.root_role_ids
        if any(role.id in roles for role in interaction.user.roles):  # type: ignore
            return True
    if privacy_policy == PrivacyPolicy.DENY:
        await interaction.followup.send(
            "This user has set their inventory to private.", ephemeral=True
        )
        return False
    elif privacy_policy == PrivacyPolicy.FRIENDS:
        if not await interacting_player.is_friend(player):
            await interaction.followup.send(
                "This users inventory can only be viewed from users they have added as friends.",
                ephemeral=True,
            )
            return False
    elif privacy_policy == PrivacyPolicy.SAME_SERVER:
        if not bot.intents.members:
            await interaction.followup.send(
                "This user has their policy set to `Same Server`, "
                "however I do not have the `members` intent to check this.",
                ephemeral=True,
            )
            return False
        if interaction.guild is None:
            await interaction.followup.send(
                "This user has set their inventory to private.", ephemeral=True
            )
            return False
        elif interaction.guild.get_member(user_obj.id) is None:
            await interaction.followup.send("This user is not in the server.", ephemeral=True)
            return False
    return True
