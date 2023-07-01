import discord
import logging
import random

from discord import app_commands
from discord.ui import Button
from discord.ext import commands
from discord.utils import format_dt
from tortoise.exceptions import IntegrityError, DoesNotExist
from typing import TYPE_CHECKING, cast
from ballsdex.core.utils.buttons import ConfirmChoiceView

from ballsdex.settings import settings
from ballsdex.core.models import GuildConfig, Player, BallInstance, BlacklistedID, BlacklistedGuild
from ballsdex.core.utils.transformers import BallTransform, SpecialTransform
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.packages.countryballs.countryball import CountryBall

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from ballsdex.packages.countryballs.cog import CountryBallsSpawner

log = logging.getLogger("ballsdex.packages.admin.cog")


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
        embed.set_author(name=guild.name, icon_url=guild.icon.url)
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

        await interaction.response.send_message(embed=embed)

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def guilds(
        self,
        interaction: discord.Interaction,
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

    @app_commands.command()
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
        log.info(
            f"{interaction.user} spawned {settings.collectible_name} {countryball.name} "
            f"in {channel or interaction.channel}."
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
            The countryball you want to give.
        user: discord.User
            The user you want to give a countryball to.
        special: Special | None
            A special background to set.
        shiny: bool
            Whether the ball will be shiny or not. Omit this to make it random.
        health_bonus: int | None
            The health bonus in percentage, positive or negative. Omit this to make it random \
(-20/+20%).
        attack_bonus: int | None
            The attack bonus in percentage, positive or negative. Omit this to make it random \
(-20/+20%).
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
            attack_bonus=attack_bonus or random.randint(-20, 20),
            health_bonus=health_bonus or random.randint(-20, 20),
            special=special,
        )
        await interaction.followup.send(
            f"`{ball.country}` {settings.collectible_name} was successfully given to `{user}`.\n"
            f"Special: `{special.name if special else None}` • ATK:`{instance.attack_bonus:+d}` • "
            f"HP:`{instance.health_bonus:+d}` • Shiny: `{instance.shiny}`"
        )
        log.info(
            f"{interaction.user} gave {settings.collectible_name} {ball.country} to {user}. "
            f"Special={special.name if special else None} ATK={instance.attack_bonus:+d} "
            f"HP={instance.health_bonus:+d} shiny={instance.shiny}"
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
            Reason for this blacklist.
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
        log.info(
            f"{interaction.user} blacklisted {user} ({user.id}) for the following reason: {reason}"
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
        log.info(f"{interaction.user} removed blacklist for user {user} ({user.id})")

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
            await interaction.response.send_message("That user isn't blacklisted.")
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
            Reason for this blacklist.
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
        log.info(
            f"{interaction.user} blacklisted {guild}({guild.id}) "
            f"for the following reason: {reason}"
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
            log.info(f"{interaction.user} removed blacklist for guild {guild} ({guild.id})")

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
            ballIdConverted = int(ball_id, 16)
        except ValueError:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True
            )
            return
        try:
            ball = await BallInstance.get(id=ballIdConverted).prefetch_related(
                "player", "trade_player", "special"
            )
        except DoesNotExist:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"**{settings.collectible_name.title()} ID:** {ball.id}\n"
            f"**Player:** {ball.player}\n"
            f"**Name:** {ball.countryball}\n"
            f"**Attack bonus:** {ball.attack_bonus}\n"
            f"**Health bonus:** {ball.health_bonus}\n"
            f"**Shiny:** {ball.shiny}\n"
            f"**Special:** {ball.special.name if ball.special else None}\n"
            f"**Caught at:** {format_dt(ball.catch_date, style='R')}\n"
            f"**Traded:** {ball.trade_player}\n"
        )

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
            ball = await BallInstance.get(id=ballIdConverted)
        except DoesNotExist:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True
            )
            return
        player, _ = await Player.get_or_create(discord_id=user.id)
        ball.player = player
        await ball.save()
        await interaction.response.send_message(
            f"{settings.collectible_name.title()} {ball.countryball} transferred to {user}.",
            ephemeral=True,
        )

    @balls.command(name="reset")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def balls_reset(self, interaction: discord.Interaction, user: discord.User):
        """
        Reset a player's balls.

        Parameters
        ----------
        user: discord.User
            The user you want to reset the balls of.
        """
        player = await Player.get(discord_id=user.id)
        if not player:
            await interaction.response.send_message(
                "The user you gave does not exist.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        view = ConfirmChoiceView(interaction)
        await interaction.followup.send(
            f"Are you sure you want to delete {user}'s {settings.collectible_name}s?",
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if not view.value:
            return
        await BallInstance.filter(player=player).delete()
        await interaction.followup.send(
            f"{user}'s {settings.collectible_name}s have been reset.", ephemeral=True
        )

    @balls.command(name="count")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def balls_count(
        self,
        interaction: discord.Interaction,
        user: discord.User = None,
        ball: BallTransform = None,
        shiny: bool = None,
        special: SpecialTransform = None,
    ):
        """
        Count the number of balls that a player has or how many exist in total.

        Parameters
        ----------
        user: discord.User
            The user you want to count the balls of.
        ball: Ball
            The ball you want to count.
        shiny: bool
            Whether the ball is shiny or not.
        special: Special
            The special background of the ball.
        """
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
        balls = await BallInstance.filter(**filters)
        country = f"{ball.country} " if ball else ""
        plural = "s" if len(balls) > 1 else ""
        special = f"{special.name} " if special else ""
        if user:
            await interaction.followup.send(
                f"{user} has {len(balls)} {special}{country}{settings.collectible_name}{plural}."
            )
        else:
            await interaction.followup.send(
                f"There are {len(balls)} {special}{country}{settings.collectible_name}{plural}."
            )
