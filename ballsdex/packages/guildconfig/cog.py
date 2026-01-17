from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.ext import commands

from bd_models.models import GuildConfig
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


@app_commands.default_permissions(manage_guild=True)
@app_commands.guild_only()
class Config(commands.GroupCog):
    """
    Configure countryball spawning for your server.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(read_messages=True, send_messages=True, embed_links=True)
    async def channel(
        self, interaction: discord.Interaction["BallsDexBot"], channel: discord.TextChannel | None = None
    ):
        """
        Set or change the channel where countryballs will spawn.

        Parameters
        ----------
        channel: discord.TextChannel
            The channel you want to set, current one if not specified.
        """
        if channel is None:
            if isinstance(interaction.channel, discord.TextChannel):
                channel = interaction.channel
            else:
                await interaction.response.send_message(
                    "The current channel is not a valid text channel.", ephemeral=True
                )
                return

        guild = interaction.guild
        assert guild

        if guild.unavailable:
            await interaction.response.send_message(
                "The server is unavailable to the bot and will not work properly. "
                "Kicking and readding the bot may fix this.",
                ephemeral=True,
            )
            return

        embed: discord.Embed | None = None
        readable_channels = len([x for x in guild.text_channels if x.permissions_for(guild.me).read_messages])

        if readable_channels / len(guild.text_channels) < 0.75:
            embed = discord.Embed(
                title="\N{WARNING SIGN}\N{VARIATION SELECTOR-16} Warning",
                description=(
                    f"This server has {len(guild.text_channels)} channels, but "
                    f"{settings.bot_name} can only read {readable_channels} channels.\n"
                    "Spawn is based on message activity, too few readable channels will result in "
                    "fewer spawns. It is recommended that you inspect your permissions."
                ),
                color=discord.Color.yellow(),
            )

        config, _ = await GuildConfig.objects.aget_or_create(guild_id=interaction.guild_id)
        config.spawn_channel = channel.id
        config.enabled = True
        await config.asave()

        interaction.client.dispatch("ballsdex_settings_change", interaction.guild, channel=self.channel, enabled=True)

        if embed:
            await channel.send(embed=embed)

        await interaction.response.send_message(
            f"The new spawn channel was successfully set to {channel.mention}.\n"
            f"{settings.plural_collectible_name.title()} will start spawning as "
            "users talk unless the bot is disabled."
        )

    @app_commands.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(send_messages=True)
    async def disable(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Disable or enable countryballs spawning.
        """
        guild = cast(discord.Guild, interaction.guild)  # guild-only command

        config, _ = await GuildConfig.objects.aget_or_create(guild_id=interaction.guild_id)
        config.enabled = not config.enabled
        await config.asave(update_fields=("enabled",))

        self.bot.dispatch("ballsdex_settings_change", guild, enabled=config.enabled)

        if not config.enabled:
            await interaction.response.send_message(
                f"{settings.bot_name} is now disabled in this server. Commands will still be "
                f"available, but the spawn of new {settings.plural_collectible_name} "
                "is suspended.\nTo re-enable the spawn, use the same command."
            )
            return

        if not config.spawn_channel:
            config_cmd = self.channel.extras.get("mention", "`/config channel`")
            await interaction.response.send_message(
                f"{settings.bot_name} is now enabled in this server, however there is no "
                f"spawning channel set. Please configure one with {config_cmd}."
            )
            return

        channel = guild.get_channel(config.spawn_channel)

        if not channel:
            await interaction.response.send_message(
                "The spawning channel specified in the configuration is not available.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"{settings.bot_name} is now enabled in this server, "
            f"{settings.plural_collectible_name} will start spawning "
            f"soon in {channel.mention}."
        )

    @app_commands.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check the server configuration status.
        """
        config = await GuildConfig.objects.aget_or_none(guild_id=interaction.guild_id)
        config_cmd = self.channel.extras.get("mention", "`/config channel`")

        if not config or not config.spawn_channel:
            await interaction.response.send_message(
                f"{settings.bot_name} is not configured in this server yet.\nPlease use {config_cmd} to set a channel."
            )
            return

        assert interaction.guild

        if interaction.guild.unavailable:
            await interaction.response.send_message("Your server is unavailable to the bot. Readding it may fix this.")
            return

        channel = interaction.guild.get_channel(config.spawn_channel)

        if channel:
            await interaction.response.send_message(
                f"{settings.bot_name} is configured in this server.\n"
                f"Spawn channel: {channel.mention}\n"
                f"Status: {'Enabled' if config.enabled else 'Disabled'}"
            )
            return

        await interaction.response.send_message(
            f"{settings.bot_name} is configured, but the specified channel could not be found.\n"
            f"Please use {config_cmd} to set it again."
        )
