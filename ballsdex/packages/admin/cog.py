import discord
import logging
import random
import sys
import os

from discord import app_commands
from discord.ext import commands
from tortoise.exceptions import IntegrityError, DoesNotExist
from typing import TYPE_CHECKING

from ballsdex.core.models import GuildConfig, Player, BallInstance, BlacklistedID
from ballsdex.core.utils.transformers import BallTransform, SpecialTransform
from ballsdex.packages.countryballs.countryball import CountryBall

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.admin.cog")

try:
    if guilds := os.environ.get("BALLSDEXBOT_ADMIN_GUILDS"):
        admin_guilds = [discord.Object(x) for x in guilds.split(",")]
    else:
        admin_guilds = []
except TypeError:
    log.critical(
        "The value of BALLSDEX_ADMIN_GUILDS is incorrect. "
        "It must be a list of guild IDs separated by commas.",
        exc_info=True,
    )
    sys.exit(1)

try:
    if roles := os.environ.get("BALLSDEXBOT_ADMIN_ROLES"):
        admin_roles = [int(x) for x in roles.split(",")]
    else:
        admin_roles = []
except ValueError:
    log.critical(
        "The value of BALLSDEX_ADMIN_ROLES is incorrect. "
        "It must be a list of role IDs separated by commas.",
        exc_info=True,
    )
    sys.exit(1)

try:
    if roles := os.environ.get("BALLSDEXBOT_ROOT_ROLES"):
        root_roles = [int(x) for x in roles.split(",")]
    else:
        root_roles = []
except ValueError:
    log.critical(
        "The value of BALLSDEX_ROOT_ROLES is incorrect. "
        "It must be a list of role IDs separated by commas.",
        exc_info=True,
    )
    sys.exit(1)


@app_commands.guilds(*admin_guilds)
@app_commands.default_permissions(administrator=True)
class Admin(commands.GroupCog):
    """
    Bot admin commands.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.blacklist.parent = self.__cog_app_commands_group__

    blacklist = app_commands.Group(name="blacklist", description="Bot blacklist management")

    @app_commands.command()
    @app_commands.checks.has_any_role(*root_roles, *admin_roles)
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
                    "The user does not own any server with Ballsdex.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "The user does not own any server with Ballsdex.\n"
                    ":warning: *The bot cannot be aware of the member's presence in servers, "
                    "it is only aware of server ownerships.*",
                    ephemeral=True,
                )
            return

        if len(guilds) > 1:
            text = f"__**{len(guilds)} servers shared with {user.mention}**__"
        else:
            text = f"__**1 server shared with {user.mention}**__\n\n"

        for guild in guilds:

            if config := await GuildConfig.get_or_none(guild_id=guild.id):
                spawn_enabled = config.enabled and config.guild_id
            else:
                spawn_enabled = False

            text += f"\n\n`{guild.id}`\n"

            # highlight suspicious server names
            if any(x in guild.name.lower() for x in ("farm", "grind", "spam")):
                text += f"- :warning: **{guild.name}**\n"
            else:
                text += f"- {guild.name}\n"

            # highlight low member count
            if guild.member_count <= 3:  # type: ignore
                text += f"- :warning: **{guild.member_count} members**\n"
            else:
                text += f"- {guild.member_count} members\n"

            # highlight if spawning is enabled
            if spawn_enabled:
                text += "- :warning: **Spawn is enabled**"
            else:
                text += "- Spawn is disabled"

        if not self.bot.intents.members:
            text += (
                "\n\n:warning: *The bot cannot be aware of the member's presence in servers, "
                "it is only aware of server ownerships.*"
            )
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command()
    @app_commands.checks.has_any_role(*root_roles)
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
        await interaction.followup.send("Ball spawned.", ephemeral=True)
        log.info(
            f"{interaction.user} spawned ball {countryball.name} "
            f"in {channel or interaction.channel}."
        )

    @app_commands.command()
    @app_commands.checks.has_any_role(*root_roles)
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
            f"`{ball.country}` ball was successfully given to `{user}`.\n"
            f"Special: `{special.name if special else None}` • ATK:`{instance.attack_bonus:+d}` • "
            f"HP:`{instance.health_bonus:+d}` • Shiny: `{instance.shiny}`"
        )
        log.info(
            f"{interaction.user} gave ball {ball.country} to {user}. "
            f"Special={special.name if special else None} ATK={instance.attack_bonus:+d} "
            f"HP={instance.health_bonus:+d} shiny={instance.shiny}"
        )

    @blacklist.command(name="add")
    @app_commands.checks.has_any_role(*root_roles, *admin_roles)
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

        final_reason = f"\nDone through the bot by {interaction.user} ({interaction.user.id})"

        try:
            await BlacklistedID.create(discord_id=user.id, reason=final_reason)
        except IntegrityError:
            await interaction.response.send_message("That user was already blacklisted.")
        else:
            self.bot.blacklist.append(user.id)
            await interaction.response.send_message("User is now blacklisted.")
        log.info(
            f"{interaction.user} blacklisted {user} ({user.id}) for the following reason: {reason}"
        )

    @blacklist.command(name="remove")
    @app_commands.checks.has_any_role(*root_roles, *admin_roles)
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
            The user you want to blacklist, if available in the current server.
        user_id: str | None
            The ID of the user you want to blacklist, if it's not in the current server.
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
            await interaction.response.send_message("That user isn't blacklisted.")
        else:
            await blacklisted.delete()
            self.bot.blacklist.remove(user.id)
            await interaction.response.send_message("User is now removed from blacklist.")
        log.info(f"{interaction.user} removed blacklist for user {user} ({user.id})")
