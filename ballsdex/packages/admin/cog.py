import datetime
import logging
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Optional, cast

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button
from discord.utils import format_dt
from tortoise.exceptions import BaseORMException, DoesNotExist, IntegrityError
from tortoise.expressions import Q

from ballsdex.core.models import (
    Ball,
    BallInstance,
    BlacklistedGuild,
    BlacklistedID,
    GuildConfig,
    Player,
    Trade,
    TradeObject,
    balls,
)
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.enums import DONATION_POLICY_MAP, PRIVATE_POLICY_MAP
from ballsdex.core.utils.logging import log_action
from ballsdex.core.utils.paginator import FieldPageSource, Pages, TextPageSource
from ballsdex.core.utils.transformers import (
    BallTransform,
    EconomyTransform,
    RegimeTransform,
    SpecialTransform,
)
from ballsdex.packages.countryballs.countryball import CountryBall
from ballsdex.packages.trade.display import TradeViewFormat, fill_trade_embed_fields
from ballsdex.packages.trade.trade_user import TradingUser
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from ballsdex.packages.countryballs.cog import CountryBallsSpawner

log = logging.getLogger("ballsdex.packages.admin.cog")
FILENAME_RE = re.compile(r"^(.+)(\.\S+)$")


async def save_file(attachment: discord.Attachment) -> Path:
    path = Path(f"./static/uploads/{attachment.filename}")
    match = FILENAME_RE.match(attachment.filename)
    if not match:
        raise TypeError("The file you uploaded lacks an extension.")
    i = 1
    while path.exists():
        path = Path(f"./static/uploads/{match.group(1)}-{i}{match.group(2)}")
        i = i + 1
    await attachment.save(path)
    return path


@app_commands.guilds(*settings.admin_guild_ids)
@app_commands.default_permissions(administrator=True)
class Admin(commands.GroupCog):
    """
    Bot admin commands.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.blacklist.parent = self.__cog_app_commands_group__
        self.balls.parent = self.__cog_app_commands_group__

    blacklist = app_commands.Group(name="blacklist", description="Bot blacklist management")
    blacklist_guild = app_commands.Group(
        name="blacklistguild", description="Guild blacklist management"
    )
    balls = app_commands.Group(
        name=settings.players_group_cog_name, description="Balls management"
    )
    logs = app_commands.Group(name="logs", description="Bot logs management")
    history = app_commands.Group(name="history", description="Trade history management")
    info = app_commands.Group(name="info", description="Information Commands")

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def status(
        self,
        interaction: discord.Interaction,
        status: discord.Status | None = None,
        name: str | None = None,
        state: str | None = None,
        activity_type: discord.ActivityType | None = None,
    ):
        """
        Change the status of the bot. Provide at least status or text.

        Parameters
        ----------
        status: discord.Status
            The status you want to set
        name: str
            Title of the activity, if not custom
        state: str
            Custom status or subtitle of the activity
        activity_type: discord.ActivityType
            The type of activity
        """
        if not status and not name and not state:
            await interaction.response.send_message(
                "You must provide at least `status`, `name` or `state`.", ephemeral=True
            )
            return

        activity: discord.Activity | None = None
        status = status or discord.Status.online
        activity_type = activity_type or discord.ActivityType.custom

        if activity_type == discord.ActivityType.custom and name and not state:
            await interaction.response.send_message(
                "You must provide `state` for custom activities. `name` is unused.", ephemeral=True
            )
            return
        if activity_type != discord.ActivityType.custom and not name:
            await interaction.response.send_message(
                "You must provide `name` for pre-defined activities.", ephemeral=True
            )
            return
        if name or state:
            activity = discord.Activity(name=name or state, state=state, type=activity_type)
        await self.bot.change_presence(status=status, activity=activity)
        await interaction.response.send_message("Status updated.", ephemeral=True)

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def rarity(self, interaction: discord.Interaction["BallsDexBot"], chunked: bool = True):
        """
        Generate a list of countryballs ranked by rarity.

        Parameters
        ----------
        chunked: bool
            Group together countryballs with the same rarity.
        """
        text = ""
        sorted_balls = sorted(balls.values(), key=lambda x: x.rarity, reverse=True)

        if chunked:
            indexes: dict[float, list[Ball]] = defaultdict(list)
            for ball in sorted_balls:
                indexes[ball.rarity].append(ball)
            for i, chunk in enumerate(indexes.values(), start=1):
                for ball in chunk:
                    text += f"{i}. {ball.country}\n"
        else:
            for i, ball in enumerate(sorted_balls, start=1):
                text += f"{i}. {ball.country}\n"

        source = TextPageSource(text, prefix="```md\n", suffix="```")
        pages = Pages(source=source, interaction=interaction, compact=True)
        await pages.start(ephemeral=True)

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def cooldown(
        self,
        interaction: discord.Interaction,
        guild_id: str | None = None,
    ):
        """
        Show the details of the spawn cooldown system for the given server

        Parameters
        ----------
        guild_id: int | None
            ID of the server you want to inspect. If not given, inspect the current server.
        """
        if guild_id:
            try:
                guild = self.bot.get_guild(int(guild_id))
            except ValueError:
                await interaction.response.send_message(
                    "Invalid guild ID. Please make sure it's a number.", ephemeral=True
                )
                return
        else:
            guild = interaction.guild
        if not guild or not guild.member_count:
            await interaction.response.send_message(
                "The given guild could not be found.", ephemeral=True
            )
            return

        spawn_manager = cast(
            "CountryBallsSpawner", self.bot.get_cog("CountryBallsSpawner")
        ).spawn_manager
        cooldown = spawn_manager.cooldowns.get(guild.id)
        if not cooldown:
            await interaction.response.send_message(
                "No spawn manager could be found for that guild. Spawn may have been disabled.",
                ephemeral=True,
            )
            return

        embed = discord.Embed()
        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
        embed.colour = discord.Colour.orange()

        delta = (interaction.created_at - cooldown.time).total_seconds()
        # change how the threshold varies according to the member count, while nuking farm servers
        if guild.member_count < 5:
            multiplier = 0.1
            range = "1-4"
        elif guild.member_count < 100:
            multiplier = 0.8
            range = "5-99"
        elif guild.member_count < 1000:
            multiplier = 0.5
            range = "100-999"
        else:
            multiplier = 0.2
            range = "1000+"

        penalities: list[str] = []
        if guild.member_count < 5 or guild.member_count > 1000:
            penalities.append("Server has less than 5 or more than 1000 members")
        if any(len(x.content) < 5 for x in cooldown.message_cache):
            penalities.append("Some cached messages are less than 5 characters long")

        authors_set = set(x.author_id for x in cooldown.message_cache)
        low_chatters = len(authors_set) < 4
        # check if one author has more than 40% of messages in cache
        major_chatter = any(
            (
                len(list(filter(lambda x: x.author_id == author, cooldown.message_cache)))
                / cooldown.message_cache.maxlen  # type: ignore
                > 0.4
            )
            for author in authors_set
        )
        # this mess is needed since either conditions make up to a single penality
        if low_chatters:
            if not major_chatter:
                penalities.append("Message cache has less than 4 chatters")
            else:
                penalities.append(
                    "Message cache has less than 4 chatters **and** "
                    "one user has more than 40% of messages within message cache"
                )
        elif major_chatter:
            if not low_chatters:
                penalities.append("One user has more than 40% of messages within cache")

        penality_multiplier = 0.5 ** len(penalities)
        if penalities:
            embed.add_field(
                name="\N{WARNING SIGN}\N{VARIATION SELECTOR-16} Penalities",
                value="Each penality divides the progress by 2\n\n- " + "\n- ".join(penalities),
            )

        chance = cooldown.chance - multiplier * (delta // 60)

        embed.description = (
            f"Manager initiated **{format_dt(cooldown.time, style='R')}**\n"
            f"Initial number of points to reach: **{cooldown.chance}**\n"
            f"Message cache length: **{len(cooldown.message_cache)}**\n\n"
            f"Time-based multiplier: **x{multiplier}** *({range} members)*\n"
            "*This affects how much the number of points to reach reduces over time*\n"
            f"Penality multiplier: **x{penality_multiplier}**\n"
            "*This affects how much a message sent increases the number of points*\n\n"
            f"__Current count: **{cooldown.amount}/{chance}**__\n\n"
        )

        informations: list[str] = []
        if cooldown.lock.locked():
            informations.append("The manager is currently on cooldown.")
        if delta < 600:
            informations.append(
                "The manager is less than 10 minutes old, balls cannot spawn at the moment."
            )
        if informations:
            embed.add_field(
                name="\N{INFORMATION SOURCE}\N{VARIATION SELECTOR-16} Informations",
                value="- " + "\n- ".join(informations),
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def guilds(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User | None = None,
        user_id: str | None = None,
    ):
        """
        Shows the guilds shared with the specified user. Provide either user or user_id

        Parameters
        ----------
        user: discord.User | None
            The user you want to check, if available in the current server.
        user_id: str | None
            The ID of the user you want to check, if it's not in the current server.
        """
        if (user and user_id) or (not user and not user_id):
            await interaction.response.send_message(
                "You must provide either `user` or `user_id`.", ephemeral=True
            )
            return

        if not user:
            try:
                user = await self.bot.fetch_user(int(user_id))  # type: ignore
            except ValueError:
                await interaction.response.send_message(
                    "The user ID you gave is not valid.", ephemeral=True
                )
                return
            except discord.NotFound:
                await interaction.response.send_message(
                    "The given user ID could not be found.", ephemeral=True
                )
                return

        if self.bot.intents.members:
            guilds = user.mutual_guilds
        else:
            guilds = [x for x in self.bot.guilds if x.owner_id == user.id]

        if not guilds:
            if self.bot.intents.members:
                await interaction.response.send_message(
                    f"The user does not own any server with {settings.bot_name}.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"The user does not own any server with {settings.bot_name}.\n"
                    ":warning: *The bot cannot be aware of the member's presence in servers, "
                    "it is only aware of server ownerships.*",
                    ephemeral=True,
                )
            return

        entries: list[tuple[str, str]] = []
        for guild in guilds:
            if config := await GuildConfig.get_or_none(guild_id=guild.id):
                spawn_enabled = config.enabled and config.guild_id
            else:
                spawn_enabled = False

            field_name = f"`{guild.id}`"
            field_value = ""

            # highlight suspicious server names
            if any(x in guild.name.lower() for x in ("farm", "grind", "spam")):
                field_value += f"- :warning: **{guild.name}**\n"
            else:
                field_value += f"- {guild.name}\n"

            # highlight low member count
            if guild.member_count <= 3:  # type: ignore
                field_value += f"- :warning: **{guild.member_count} members**\n"
            else:
                field_value += f"- {guild.member_count} members\n"

            # highlight if spawning is enabled
            if spawn_enabled:
                field_value += "- :warning: **Spawn is enabled**"
            else:
                field_value += "- Spawn is disabled"

            entries.append((field_name, field_value))

        source = FieldPageSource(entries, per_page=25, inline=True)
        source.embed.set_author(name=f"{user} ({user.id})", icon_url=user.display_avatar.url)

        if len(guilds) > 1:
            source.embed.title = f"{len(guilds)} servers shared"
        else:
            source.embed.title = "1 server shared"

        if not self.bot.intents.members:
            source.embed.set_footer(
                text="\N{WARNING SIGN} The bot cannot be aware of the member's "
                "presence in servers, it is only aware of server ownerships."
            )

        pages = Pages(source=source, interaction=interaction, compact=True)
        pages.add_item(
            Button(
                style=discord.ButtonStyle.link,
                label="View profile",
                url=f"discord://-/users/{user.id}",
                emoji="\N{LEFT-POINTING MAGNIFYING GLASS}",
            )
        )
        await pages.start(ephemeral=True)

    @balls.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def spawn(
        self,
        interaction: discord.Interaction,
        ball: BallTransform | None = None,
        channel: discord.TextChannel | None = None,
    ):
        """
        Force spawn a random or specified ball.

        Parameters
        ----------
        ball: Ball | None
            The countryball you want to spawn. Random according to rarities if not specified.
        channel: discord.TextChannel | None
            The channel you want to spawn the countryball in. Current channel if not specified.
        """
        # the transformer triggered a response, meaning user tried an incorrect input
        if interaction.response.is_done():
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not ball:
            countryball = await CountryBall.get_random()
        else:
            countryball = CountryBall(ball)
        await countryball.spawn(channel or interaction.channel)  # type: ignore
        await interaction.followup.send(
            f"{settings.collectible_name.title()} spawned.", ephemeral=True
        )
        await log_action(
            f"{interaction.user} spawned {settings.collectible_name} {countryball.name} "
            f"in {channel or interaction.channel}.",
            self.bot,
        )

    @balls.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def give(
        self,
        interaction: discord.Interaction,
        ball: BallTransform,
        user: discord.User,
        special: SpecialTransform | None = None,
        shiny: bool | None = None,
        health_bonus: int | None = None,
        attack_bonus: int | None = None,
    ):
        """
        Give the specified countryball to a player.

        Parameters
        ----------
        ball: Ball
        user: discord.User
        special: Special | None
        shiny: bool
            Omit this to make it random.
        health_bonus: int | None
            Omit this to make it random (-20/+20%).
        attack_bonus: int | None
            Omit this to make it random (-20/+20%).
        """
        # the transformers triggered a response, meaning user tried an incorrect input
        if interaction.response.is_done():
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        player, created = await Player.get_or_create(discord_id=user.id)
        instance = await BallInstance.create(
            ball=ball,
            player=player,
            shiny=(shiny if shiny is not None else random.randint(1, 2048) == 1),
            attack_bonus=(attack_bonus if attack_bonus is not None else random.randint(-20, 20)),
            health_bonus=(health_bonus if health_bonus is not None else random.randint(-20, 20)),
            special=special,
        )
        await interaction.followup.send(
            f"`{ball.country}` {settings.collectible_name} was successfully given to `{user}`.\n"
            f"Special: `{special.name if special else None}` • ATK:`{instance.attack_bonus:+d}` • "
            f"HP:`{instance.health_bonus:+d}` • Shiny: `{instance.shiny}`"
        )
        await log_action(
            f"{interaction.user} gave {settings.collectible_name} {ball.country} to {user}. "
            f"(Special={special.name if special else None} ATK={instance.attack_bonus:+d} "
            f"HP={instance.health_bonus:+d} shiny={instance.shiny}).",
            self.bot,
        )

    @blacklist.command(name="add")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def blacklist_add(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
        user_id: str | None = None,
        reason: str | None = None,
    ):
        """
        Add a user to the blacklist. No reload is needed.

        Parameters
        ----------
        user: discord.User | None
            The user you want to blacklist, if available in the current server.
        user_id: str | None
            The ID of the user you want to blacklist, if it's not in the current server.
        reason: str | None
        """
        if (user and user_id) or (not user and not user_id):
            await interaction.response.send_message(
                "You must provide either `user` or `user_id`.", ephemeral=True
            )
            return

        if not user:
            try:
                user = await self.bot.fetch_user(int(user_id))  # type: ignore
            except ValueError:
                await interaction.response.send_message(
                    "The user ID you gave is not valid.", ephemeral=True
                )
                return
            except discord.NotFound:
                await interaction.response.send_message(
                    "The given user ID could not be found.", ephemeral=True
                )
                return

        final_reason = (
            f"{reason}\nDone through the bot by {interaction.user} ({interaction.user.id})"
        )

        try:
            await BlacklistedID.create(discord_id=user.id, reason=final_reason)
        except IntegrityError:
            await interaction.response.send_message(
                "That user was already blacklisted.", ephemeral=True
            )
        else:
            self.bot.blacklist.add(user.id)
            await interaction.response.send_message("User is now blacklisted.", ephemeral=True)
        await log_action(
            f"{interaction.user} blacklisted {user} ({user.id})"
            f" for the following reason: {reason}.",
            self.bot,
        )

    @blacklist.command(name="remove")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def blacklist_remove(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
        user_id: str | None = None,
    ):
        """
        Remove a user from the blacklist. No reload is needed.

        Parameters
        ----------
        user: discord.User | None
            The user you want to unblacklist, if available in the current server.
        user_id: str | None
            The ID of the user you want to unblacklist, if it's not in the current server.
        """
        if (user and user_id) or (not user and not user_id):
            await interaction.response.send_message(
                "You must provide either `user` or `user_id`.", ephemeral=True
            )
            return

        if not user:
            try:
                user = await self.bot.fetch_user(int(user_id))  # type: ignore
            except ValueError:
                await interaction.response.send_message(
                    "The user ID you gave is not valid.", ephemeral=True
                )
                return
            except discord.NotFound:
                await interaction.response.send_message(
                    "The given user ID could not be found.", ephemeral=True
                )
                return

        try:
            blacklisted = await BlacklistedID.get(discord_id=user.id)
        except DoesNotExist:
            await interaction.response.send_message("That user isn't blacklisted.", ephemeral=True)
        else:
            await blacklisted.delete()
            self.bot.blacklist.remove(user.id)
            await interaction.response.send_message(
                "User is now removed from blacklist.", ephemeral=True
            )
        await log_action(
            f"{interaction.user} removed blacklist for user {user} ({user.id}).", self.bot
        )

    @blacklist.command(name="info")
    async def blacklist_info(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
        user_id: str | None = None,
    ):
        """
        Check if a user is blacklisted and show the corresponding reason.

        Parameters
        ----------
        user: discord.User | None
            The user you want to check, if available in the current server.
        user_id: str | None
            The ID of the user you want to check, if it's not in the current server.
        """
        if (user and user_id) or (not user and not user_id):
            await interaction.response.send_message(
                "You must provide either `user` or `user_id`.", ephemeral=True
            )
            return

        if not user:
            try:
                user = await self.bot.fetch_user(int(user_id))  # type: ignore
            except ValueError:
                await interaction.response.send_message(
                    "The user ID you gave is not valid.", ephemeral=True
                )
                return
            except discord.NotFound:
                await interaction.response.send_message(
                    "The given user ID could not be found.", ephemeral=True
                )
                return
        # We assume that we have a valid discord.User object at this point.

        try:
            blacklisted = await BlacklistedID.get(discord_id=user.id)
        except DoesNotExist:
            await interaction.response.send_message("That user isn't blacklisted.", ephemeral=True)
        else:
            if blacklisted.date:
                await interaction.response.send_message(
                    f"`{user}` (`{user.id}`) was blacklisted on {format_dt(blacklisted.date)}"
                    f"({format_dt(blacklisted.date, style='R')}) for the following reason:\n"
                    f"{blacklisted.reason}",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"`{user}` (`{user.id}`) is currently blacklisted (date unknown)"
                    " for the following reason:\n"
                    f"{blacklisted.reason}",
                    ephemeral=True,
                )

    @blacklist_guild.command(name="add")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def blacklist_add_guild(
        self,
        interaction: discord.Interaction,
        guild_id: str,
        reason: str,
    ):
        """
        Add a guild to the blacklist. No reload is needed.

        Parameters
        ----------
        guild_id: str
            The ID of the user you want to blacklist, if it's not in the current server.
        reason: str
        """

        try:
            guild = await self.bot.fetch_guild(int(guild_id))  # type: ignore
        except ValueError:
            await interaction.response.send_message(
                "The guild ID you gave is not valid.", ephemeral=True
            )
            return
        except discord.NotFound:
            await interaction.response.send_message(
                "The given guild ID could not be found.", ephemeral=True
            )
            return

        final_reason = f"{reason}\nBy: {interaction.user} ({interaction.user.id})"

        try:
            await BlacklistedGuild.create(discord_id=guild.id, reason=final_reason)
        except IntegrityError:
            await interaction.response.send_message(
                "That guild was already blacklisted.", ephemeral=True
            )
        else:
            self.bot.blacklist_guild.add(guild.id)
            await interaction.response.send_message("Guild is now blacklisted.", ephemeral=True)
        await log_action(
            f"{interaction.user} blacklisted the guild {guild}({guild.id}) "
            f"for the following reason: {reason}.",
            self.bot,
        )

    @blacklist_guild.command(name="remove")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def blacklist_remove_guild(
        self,
        interaction: discord.Interaction,
        guild_id: str,
    ):
        """
        Remove a guild from the blacklist. No reload is needed.

        Parameters
        ----------
        guild_id: str
            The ID of the user you want to unblacklist, if it's not in the current server.
        """

        try:
            guild = await self.bot.fetch_guild(int(guild_id))  # type: ignore
        except ValueError:
            await interaction.response.send_message(
                "The user ID you gave is not valid.", ephemeral=True
            )
            return
        except discord.NotFound:
            await interaction.response.send_message(
                "The given user ID could not be found.", ephemeral=True
            )
            return

        try:
            blacklisted = await BlacklistedGuild.get(discord_id=guild.id)
        except DoesNotExist:
            await interaction.response.send_message(
                "That guild isn't blacklisted.", ephemeral=True
            )
        else:
            await blacklisted.delete()
            self.bot.blacklist_guild.remove(guild.id)
            await interaction.response.send_message(
                "Guild is now removed from blacklist.", ephemeral=True
            )
            await log_action(
                f"{interaction.user} removed blacklist for guild {guild} ({guild.id}).", self.bot
            )

    @blacklist_guild.command(name="info")
    async def blacklist_info_guild(
        self,
        interaction: discord.Interaction,
        guild_id: str,
    ):
        """
        Check if a guild is blacklisted and show the corresponding reason.

        Parameters
        ----------
        guild_id: str
            The ID of the user you want to check, if it's not in the current server.
        """

        try:
            guild = await self.bot.fetch_guild(int(guild_id))  # type: ignore
        except ValueError:
            await interaction.response.send_message(
                "The guild ID you gave is not valid.", ephemeral=True
            )
            return
        except discord.NotFound:
            await interaction.response.send_message(
                "The given guild ID could not be found.", ephemeral=True
            )
            return

        try:
            blacklisted = await BlacklistedGuild.get(discord_id=guild.id)
        except DoesNotExist:
            await interaction.response.send_message("That guild isn't blacklisted.")
        else:
            if blacklisted.date:
                await interaction.response.send_message(
                    f"`{guild}` (`{guild.id}`) was blacklisted on {format_dt(blacklisted.date)}"
                    f"({format_dt(blacklisted.date, style='R')}) for the following reason:\n"
                    f"{blacklisted.reason}",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"`{guild}` (`{guild.id}`) is currently blacklisted (date unknown)"
                    " for the following reason:\n"
                    f"{blacklisted.reason}",
                    ephemeral=True,
                )

    @balls.command(name="info")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def balls_info(self, interaction: discord.Interaction, ball_id: str):
        """
        Show information about a ball.

        Parameters
        ----------
        ball_id: str
            The ID of the ball you want to get information about.
        """
        try:
            pk = int(ball_id, 16)
        except ValueError:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True
            )
            return
        try:
            ball = await BallInstance.get(id=pk).prefetch_related(
                "player", "trade_player", "special"
            )
        except DoesNotExist:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True
            )
            return
        spawned_time = format_dt(ball.spawned_time, style="R") if ball.spawned_time else "N/A"
        catch_time = (
            (ball.catch_date - ball.spawned_time).total_seconds()
            if ball.catch_date and ball.spawned_time
            else "N/A"
        )
        await interaction.response.send_message(
            f"**{settings.collectible_name.title()} ID:** {ball.pk}\n"
            f"**Player:** {ball.player}\n"
            f"**Name:** {ball.countryball}\n"
            f"**Attack bonus:** {ball.attack_bonus}\n"
            f"**Health bonus:** {ball.health_bonus}\n"
            f"**Shiny:** {ball.shiny}\n"
            f"**Special:** {ball.special.name if ball.special else None}\n"
            f"**Caught at:** {format_dt(ball.catch_date, style='R')}\n"
            f"**Spawned at:** {spawned_time}\n"
            f"**Catch time:** {catch_time} seconds\n"
            f"**Caught in:** {ball.server_id if ball.server_id else 'N/A'}\n"
            f"**Traded:** {ball.trade_player}\n",
            ephemeral=True,
        )
        await log_action(f"{interaction.user} got info for {ball}({ball.pk}).", self.bot)

    @balls.command(name="delete")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def balls_delete(self, interaction: discord.Interaction, ball_id: str):
        """
        Delete a ball.

        Parameters
        ----------
        ball_id: str
            The ID of the ball you want to get information about.
        """
        try:
            ballIdConverted = int(ball_id, 16)
        except ValueError:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True
            )
            return
        try:
            ball = await BallInstance.get(id=ballIdConverted)
        except DoesNotExist:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True
            )
            return
        await ball.delete()
        await interaction.response.send_message(
            f"{settings.collectible_name.title()} {ball_id} deleted.", ephemeral=True
        )
        await log_action(f"{interaction.user} deleted {ball}({ball.pk}).", self.bot)

    @balls.command(name="transfer")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def balls_transfer(
        self, interaction: discord.Interaction, ball_id: str, user: discord.User
    ):
        """
        Transfer a ball to another user.

        Parameters
        ----------
        ball_id: str
            The ID of the ball you want to get information about.
        user: discord.User
            The user you want to transfer the ball to.
        """
        try:
            ballIdConverted = int(ball_id, 16)
        except ValueError:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True
            )
            return
        try:
            ball = await BallInstance.get(id=ballIdConverted).prefetch_related("player")
            original_player = ball.player
        except DoesNotExist:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True
            )
            return
        player, _ = await Player.get_or_create(discord_id=user.id)
        ball.player = player
        await ball.save()

        trade = await Trade.create(player1=original_player, player2=player)
        await TradeObject.create(trade=trade, ballinstance=ball, player=original_player)
        await interaction.response.send_message(
            f"Transfered {ball}({ball.pk}) from {original_player} to {user}.",
            ephemeral=True,
        )
        await log_action(
            f"{interaction.user} transferred {ball}({ball.pk}) from {original_player} to {user}.",
            self.bot,
        )

    @balls.command(name="reset")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def balls_reset(
        self, interaction: discord.Interaction, user: discord.User, percentage: int | None = None
    ):
        """
        Reset a player's balls.

        Parameters
        ----------
        user: discord.User
            The user you want to reset the balls of.
        percentage: int | None
            The percentage of balls to delete, if not all. Used for sanctions.
        """
        player = await Player.get(discord_id=user.id)
        if not player:
            await interaction.response.send_message(
                "The user you gave does not exist.", ephemeral=True
            )
            return
        if percentage and not 0 < percentage < 100:
            await interaction.response.send_message(
                "The percentage must be between 1 and 99.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not percentage:
            text = f"Are you sure you want to delete {user}'s {settings.collectible_name}s?"
        else:
            text = (
                f"Are you sure you want to delete {percentage}% of "
                f"{user}'s {settings.collectible_name}s?"
            )
        view = ConfirmChoiceView(interaction)
        await interaction.followup.send(
            text,
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if not view.value:
            return
        if percentage:
            balls = await BallInstance.filter(player=player)
            to_delete = random.sample(balls, int(len(balls) * (percentage / 100)))
            for ball in to_delete:
                await ball.delete()
            count = len(to_delete)
        else:
            count = await BallInstance.filter(player=player).delete()
        await interaction.followup.send(
            f"{count} {settings.collectible_name}s from {user} have been reset.", ephemeral=True
        )
        await log_action(
            f"{interaction.user} deleted {percentage or 100}% of "
            f"{player}'s {settings.collectible_name}s.",
            self.bot,
        )

    @balls.command(name="count")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def balls_count(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
        ball: BallTransform | None = None,
        shiny: bool | None = None,
        special: SpecialTransform | None = None,
    ):
        """
        Count the number of balls that a player has or how many exist in total.

        Parameters
        ----------
        user: discord.User
            The user you want to count the balls of.
        ball: Ball
        shiny: bool
        special: Special
        """
        if interaction.response.is_done():
            return
        filters = {}
        if ball:
            filters["ball"] = ball
        if shiny is not None:
            filters["shiny"] = shiny
        if special:
            filters["special"] = special
        if user:
            filters["player__discord_id"] = user.id
        await interaction.response.defer(ephemeral=True, thinking=True)
        balls = await BallInstance.filter(**filters).count()
        country = f"{ball.country} " if ball else ""
        plural = "s" if balls > 1 or balls == 0 else ""
        special_str = f"{special.name} " if special else ""
        shiny_str = "shiny " if shiny else ""
        if user:
            await interaction.followup.send(
                f"{user} has {balls} {special_str}{shiny_str}"
                f"{country}{settings.collectible_name}{plural}."
            )
        else:
            await interaction.followup.send(
                f"There are {balls} {special_str}{shiny_str}"
                f"{country}{settings.collectible_name}{plural}."
            )

    @balls.command(name="create")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def balls_create(
        self,
        interaction: discord.Interaction,
        *,
        name: app_commands.Range[str, None, 48],
        regime: RegimeTransform,
        health: int,
        attack: int,
        emoji_id: app_commands.Range[str, 17, 21],
        capacity_name: app_commands.Range[str, None, 64],
        capacity_description: app_commands.Range[str, None, 256],
        collection_card: discord.Attachment,
        image_credits: str,
        economy: EconomyTransform | None = None,
        rarity: float = 0.0,
        enabled: bool = False,
        tradeable: bool = False,
        wild_card: discord.Attachment | None = None,
    ):
        """
        Shortcut command for creating countryballs. They are disabled by default.

        Parameters
        ----------
        name: str
        regime: Regime
        economy: Economy | None
        health: int
        attack: int
        emoji_id: str
            An emoji ID, the bot will check if it can access the custom emote
        capacity_name: str
        capacity_description: str
        collection_card: discord.Attachment
        image_credits: str
        rarity: float
            Value defining the rarity of this countryball, if enabled
        enabled: bool
            If true, the countryball can spawn and will show up in global completion
        tradeable: bool
            If false, all instances are untradeable
        wild_card: discord.Attachment
            Artwork used to spawn the countryball, with a default
        """
        if regime is None or interaction.response.is_done():  # economy autocomplete failed
            return

        if not emoji_id.isnumeric():
            await interaction.response.send_message(
                "`emoji_id` is not a valid number.", ephemeral=True
            )
            return
        emoji = self.bot.get_emoji(int(emoji_id))
        if not emoji:
            await interaction.response.send_message(
                "The bot does not have access to the given emoji.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        default_path = Path("./ballsdex/core/image_generator/src/default.png")
        missing_default = ""
        if not wild_card and not default_path.exists():
            missing_default = (
                "**Warning:** The default spawn image is not set. This will result in errors when "
                f"attempting to spawn this {settings.collectible_name}. You can edit this on the "
                "web panel or add an image at `./ballsdex/core/image_generator/src/default.png`.\n"
            )

        try:
            collection_card_path = await save_file(collection_card)
        except Exception as e:
            log.exception("Failed saving file when creating countryball", exc_info=True)
            await interaction.followup.send(
                f"Failed saving the attached file: {collection_card.url}.\n"
                f"Partial error: {', '.join(str(x) for x in e.args)}\n"
                "The full error is in the bot logs."
            )
            return
        try:
            wild_card_path = await save_file(wild_card) if wild_card else default_path
        except Exception as e:
            log.exception("Failed saving file when creating countryball", exc_info=True)
            await interaction.followup.send(
                f"Failed saving the attached file: {collection_card.url}.\n"
                f"Partial error: {', '.join(str(x) for x in e.args)}\n"
                "The full error is in the bot logs."
            )
            return

        try:
            ball = await Ball.create(
                country=name,
                regime=regime,
                economy=economy,
                health=health,
                attack=attack,
                rarity=rarity,
                enabled=enabled,
                tradeable=tradeable,
                emoji_id=emoji_id,
                wild_card="/" + str(wild_card_path),
                collection_card="/" + str(collection_card_path),
                credits=image_credits,
                capacity_name=capacity_name,
                capacity_description=capacity_description,
            )
        except BaseORMException as e:
            log.exception("Failed creating countryball with admin command", exc_info=True)
            await interaction.followup.send(
                f"Failed creating the {settings.collectible_name}.\n"
                f"Partial error: {', '.join(str(x) for x in e.args)}\n"
                "The full error is in the bot logs."
            )
        else:
            files = [await collection_card.to_file()]
            if wild_card:
                files.append(await wild_card.to_file())
            await self.bot.load_cache()
            await interaction.followup.send(
                f"Successfully created a {settings.collectible_name} with ID {ball.pk}! "
                "The internal cache was reloaded.\n"
                f"{missing_default}\n"
                f"{name=} regime={regime.name} economy={economy.name if economy else None} "
                f"{health=} {attack=} {rarity=} {enabled=} {tradeable=} emoji={emoji}",
                files=files,
            )

    @logs.command(name="catchlogs")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def logs_add(
        self,
        interaction: discord.Interaction,
        user: discord.User,
    ):
        """
        Add or remove a user from catch logs.

        Parameters
        ----------
        user: discord.User
            The user you want to add or remove to the logs.
        """
        if user.id in self.bot.catch_log:
            self.bot.catch_log.remove(user.id)
            await interaction.response.send_message(
                f"{user} removed from catch logs.", ephemeral=True
            )
        else:
            self.bot.catch_log.add(user.id)
            await interaction.response.send_message(f"{user} added to catch logs.", ephemeral=True)

    @logs.command(name="commandlogs")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def commandlogs_add(
        self,
        interaction: discord.Interaction,
        user: discord.User,
    ):
        """
        Add or remove a user from command logs.

        Parameters
        ----------
        user: discord.User
            The user you want to add or remove to the logs.
        """
        if user.id in self.bot.command_log:
            self.bot.command_log.remove(user.id)
            await interaction.response.send_message(
                f"{user} removed from command logs.", ephemeral=True
            )
        else:
            self.bot.command_log.add(user.id)
            await interaction.response.send_message(
                f"{user} added to command logs.", ephemeral=True
            )

    @history.command(name="user")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    @app_commands.choices(
        sorting=[
            app_commands.Choice(name="Most Recent", value="-date"),
            app_commands.Choice(name="Oldest", value="date"),
        ]
    )
    async def history_user(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
        sorting: app_commands.Choice[str],
        user2: Optional[discord.User] = None,
        days: Optional[int] = None,
    ):
        """
        Show the history of a user.

        Parameters
        ----------
        user: discord.User
            The user you want to check the history of.
        sorting: str
            The sorting method you want to use.
        user2: discord.User | None
            The second user you want to check the history of.
        days: Optional[int]
            Retrieve trade history from last x days.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        if days is not None and days < 0:
            await interaction.followup.send(
                "Invalid number of days. Please provide a non-negative value.", ephemeral=True
            )
            return

        queryset = Trade.all()
        if user2:
            queryset = queryset.filter(
                (Q(player1__discord_id=user.id) & Q(player2__discord_id=user2.id))
                | (Q(player1__discord_id=user2.id) & Q(player2__discord_id=user.id))
            )
        else:
            queryset = queryset.filter(
                Q(player1__discord_id=user.id) | Q(player2__discord_id=user.id)
            )

        if days is not None and days > 0:
            end_date = datetime.datetime.now()
            start_date = end_date - datetime.timedelta(days=days)
            queryset = queryset.filter(date__range=(start_date, end_date))

        queryset = queryset.order_by(sorting.value).prefetch_related("player1", "player2")
        history = await queryset

        if not history:
            await interaction.followup.send("No history found.", ephemeral=True)
            return

        if user2:
            await interaction.followup.send(
                f"History of {user.display_name} and {user2.display_name}:"
            )

        source = TradeViewFormat(history, user.display_name, self.bot)
        pages = Pages(source=source, interaction=interaction)
        await pages.start(ephemeral=True)

    @history.command(name="ball")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    @app_commands.choices(
        sorting=[
            app_commands.Choice(name="Most Recent", value="-date"),
            app_commands.Choice(name="Oldest", value="date"),
        ]
    )
    async def history_ball(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        ballid: str,
        sorting: app_commands.Choice[str],
        days: Optional[int] = None,
    ):
        """
        Show the history of a ball.

        Parameters
        ----------
        ballid: str
            The ID of the ball you want to check the history of.
        sorting: str
            The sorting method you want to use.
        days: Optional[int]
            Retrieve ball history from last x days.
        """

        try:
            pk = int(ballid, 16)
        except ValueError:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True
            )
            return

        ball = await BallInstance.get(id=pk)
        if not ball:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        if days is not None and days < 0:
            await interaction.followup.send(
                "Invalid number of days. Please provide a non-negative value.", ephemeral=True
            )
            return

        queryset = Trade.all()
        if days is None or days == 0:
            queryset = queryset.filter(tradeobjects__ballinstance_id=pk)
        else:
            end_date = datetime.datetime.now()
            start_date = end_date - datetime.timedelta(days=days)
            queryset = queryset.filter(
                tradeobjects__ballinstance_id=pk, date__range=(start_date, end_date)
            )
        trades = await queryset.order_by(sorting.value).prefetch_related("player1", "player2")

        if not trades:
            await interaction.followup.send("No history found.", ephemeral=True)
            return

        source = TradeViewFormat(trades, f"{settings.collectible_name} {ball}", self.bot)
        pages = Pages(source=source, interaction=interaction)
        await pages.start(ephemeral=True)

    @history.command(name="trade")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def trade_info(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        tradeid: str,
    ):
        """
        Show the contents of a certain trade.

        Parameters
        ----------
        tradeid: str
            The ID of the trade you want to check the history of.
        """
        try:
            pk = int(tradeid, 16)
        except ValueError:
            await interaction.response.send_message(
                "The trade ID you gave is not valid.", ephemeral=True
            )
            return
        trade = await Trade.get(id=pk).prefetch_related("player1", "player2")
        if not trade:
            await interaction.response.send_message(
                "The trade ID you gave does not exist.", ephemeral=True
            )
            return
        embed = discord.Embed(
            title=f"Trade {trade.pk:0X}",
            description=f"Trade ID: {trade.pk:0X}",
            timestamp=trade.date,
        )
        embed.set_footer(text="Trade date: ")
        fill_trade_embed_fields(
            embed,
            self.bot,
            await TradingUser.from_trade_model(trade, trade.player1, self.bot),
            await TradingUser.from_trade_model(trade, trade.player2, self.bot),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @info.command()
    async def guild(
        self,
        interaction: discord.Interaction,
        guild_id: str,
        days: int = 7,
    ):
        """
        Show information about the server provided

        Parameters
        ----------
        guild: discord.Guild | None
            The guild you want to get information about.
        guild_id: str | None
            The ID of the guild you want to get information about.
        days: int
            The amount of days to look back for the amount of balls caught.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = self.bot.get_guild(int(guild_id))

        if not guild:
            try:
                guild = await self.bot.fetch_guild(int(guild_id))  # type: ignore
            except ValueError:
                await interaction.followup.send(
                    "The guild ID you gave is not valid.", ephemeral=True
                )
                return
            except discord.NotFound:
                await interaction.followup.send(
                    "The given guild ID could not be found.", ephemeral=True
                )
                return

        if config := await GuildConfig.get_or_none(guild_id=guild.id):
            spawn_enabled = config.enabled and config.guild_id
        else:
            spawn_enabled = False

        total_server_balls = await BallInstance.filter(
            catch_date__gte=datetime.datetime.now() - datetime.timedelta(days=days),
            server_id=guild.id,
        ).prefetch_related("player")
        if guild.owner_id:
            owner = await self.bot.fetch_user(guild.owner_id)
            embed = discord.Embed(
                title=f"{guild.name} ({guild.id})",
                description=f"Owner: {owner} ({guild.owner_id})",
                color=discord.Color.blurple(),
            )
        else:
            embed = discord.Embed(
                title=f"{guild.name} ({guild.id})",
                color=discord.Color.blurple(),
            )
        embed.add_field(name="Members", value=guild.member_count)
        embed.add_field(name="Spawn Enabled", value=spawn_enabled)
        embed.add_field(name="Created at", value=format_dt(guild.created_at, style="R"))
        embed.add_field(
            name=f"{settings.collectible_name} Caught ({days} days)",
            value=len(total_server_balls),
        )
        embed.add_field(
            name=f"Amount of Users who caught {settings.collectible_name} ({days} days)",
            value=len(set([x.player.discord_id for x in total_server_balls])),
        )
        embed.set_thumbnail(url=guild.icon.url)  # type: ignore
        await interaction.followup.send(embed=embed, ephemeral=True)

    @info.command()
    async def user(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        days: int = 7,
    ):
        """
        Show information about the user provided

        Parameters
        ----------
        user: discord.User | None
            The user you want to get information about.
        days: int
            The amount of days to look back for the amount of balls caught.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        player = await Player.get_or_none(discord_id=user.id)
        if not player:
            await interaction.followup.send("The user you gave does not exist.", ephemeral=True)
            return
        total_user_balls = await BallInstance.filter(
            catch_date__gte=datetime.datetime.now() - datetime.timedelta(days=days),
            player=player,
        )
        embed = discord.Embed(
            title=f"{user} ({user.id})",
            description=(
                f"Privacy Policy: {PRIVATE_POLICY_MAP[player.privacy_policy]}\n"
                f"Donation Policy: {DONATION_POLICY_MAP[player.donation_policy]}"
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(name=f"Balls Caught ({days} days)", value=len(total_user_balls))
        embed.add_field(
            name=f"{settings.collectible_name} Caught (Unique - ({days} days))",
            value=len(set(total_user_balls)),
        )
        embed.add_field(
            name=f"Total Server with {settings.collectible_name}s caught ({days} days))",
            value=len(set([x.server_id for x in total_user_balls])),
        )
        embed.add_field(
            name=f"Total {settings.collectible_name}s Caught",
            value=await BallInstance.filter(player__discord_id=user.id).count(),
        )
        embed.add_field(
            name=f"Total Unique {settings.collectible_name}s Caught",
            value=len(set([x.countryball for x in total_user_balls])),
        )
        embed.add_field(
            name=f"Total Server with {settings.collectible_name}s Caught",
            value=len(set([x.server_id for x in total_user_balls])),
        )
        embed.set_thumbnail(url=user.display_avatar)  # type: ignore
        await interaction.followup.send(embed=embed, ephemeral=True)
