from typing import TYPE_CHECKING, Optional, cast

import discord
from discord import app_commands
from discord.ext import commands

from bd_models.models import GuildConfig
from settings.models import settings

from .components import AcceptTOSView

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

activation_embed = discord.Embed(
    colour=0x00D936,
    title=f"{settings.bot_name} activation",
    description=f"To enable {settings.bot_name} in your server, you must "
    f"read and accept the [Terms of Service]({settings.terms_of_service}).\n\n"
    "As a summary, these are the rules of the bot:\n"
    f"- No farming (spamming or creating servers for {settings.plural_collectible_name})\n"
    f"- Selling or exchanging {settings.plural_collectible_name} "
    "against money or other goods is forbidden\n"
    "- Do not attempt to abuse the bot's internals\n"
    "**Not respecting these rules will lead to a blacklist**",
)


@app_commands.default_permissions(manage_guild=True)
@app_commands.guild_only()
class Config(commands.GroupCog):
    """
    View and manage your countryballs collection.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(read_messages=True, send_messages=True, embed_links=True)
    async def channel(
        self, interaction: discord.Interaction["BallsDexBot"], channel: Optional[discord.TextChannel] = None
    ):
        """
        Set or change the channel where countryballs will spawn.

        Parameters
        ----------
        channel: discord.TextChannel
            The channel you want to set, current one if not specified.
        """
        user = cast(discord.Member, interaction.user)

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

        channel_perms = channel.permissions_for(guild.me)
        missing_perms = [
            name
            for name, granted in (
                ("Read Messages", channel_perms.read_messages),
                ("Send Messages", channel_perms.send_messages),
                ("Embed Links", channel_perms.embed_links),
            )
            if not granted
        ]
        if missing_perms:
            await interaction.response.send_message(
                f"{settings.bot_name} is missing the following permission(s) in {channel.mention}: "
                f"**{', '.join(missing_perms)}**. Please grant them, then try again.",
                ephemeral=True,
            )
            return

        view = AcceptTOSView(interaction, channel, user)
        embed = activation_embed.copy()

        readable_channels = len([x for x in guild.text_channels if x.permissions_for(guild.me).read_messages])
        if readable_channels / len(guild.text_channels) < 0.75:
            embed.add_field(
                name="\N{WARNING SIGN}\N{VARIATION SELECTOR-16} Warning",
                value=f"This server has {len(guild.text_channels)} channels, but "
                f"{settings.bot_name} can only read {readable_channels} channels.\n"
                "Spawn is based on message activity, too few readable channels will result in "
                "fewer spawns. It is recommended that you inspect your permissions.",
            )
        message = await channel.send(embed=embed, view=view)
        view.message = message

        await interaction.response.send_message(
            f"The activation embed has been sent in {channel.mention}. Once accepted, "
            f"{settings.plural_collectible_name} will start spawning there based on message activity - "
            "send a few messages to trigger a test spawn.",
            ephemeral=True,
        )

    @app_commands.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(send_messages=True)
    async def disable(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Disable or enable countryballs spawning.
        """
        guild = cast(discord.Guild, interaction.guild)  # guild-only command
        config, created = await GuildConfig.objects.aget_or_create(guild_id=interaction.guild_id)
        if config.enabled:
            config.enabled = False  # type: ignore
            await config.asave()
            self.bot.dispatch("ballsdex_settings_change", guild, enabled=False)
            await interaction.response.send_message(
                f"Spawning is now **disabled** in this server. Commands will still be "
                f"available, but the spawn of new {settings.plural_collectible_name} "
                "is suspended.\nTo re-enable the spawn, use the same command."
            )
        else:
            config.enabled = True  # type: ignore
            await config.asave()
            self.bot.dispatch("ballsdex_settings_change", guild, enabled=True)
            if config.spawn_channel and (channel := guild.get_channel(config.spawn_channel)):
                if channel:
                    await interaction.response.send_message(
                        f"Spawning is now **enabled** in this server, "
                        f"{settings.plural_collectible_name} will start spawning "
                        f"soon in {channel.mention}."
                    )
                else:
                    await interaction.response.send_message(
                        "The spawning channel specified in the configuration is not available.", ephemeral=True
                    )
            else:
                config_cmd = self.channel.extras.get("mention", "`/config channel`")
                await interaction.response.send_message(
                    f"Spawning is now **enabled** in this server, however there is no "
                    f"spawning channel set. Please configure one with {config_cmd}."
                )

    @app_commands.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(send_messages=True)
    async def toggledrop(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Allow or disallow players from using the drop command in this server.
        """
        config, created = await GuildConfig.objects.aget_or_create(guild_id=interaction.guild_id)
        config.manual_drop_enabled = not config.manual_drop_enabled  # type: ignore
        await config.asave()
        if config.manual_drop_enabled:
            await interaction.response.send_message(
                f"Players can now use the drop command to manually spawn {settings.plural_collectible_name}."
            )
        else:
            await interaction.response.send_message(
                f"Players can no longer use the drop command to manually spawn {settings.plural_collectible_name}."
            )

    @app_commands.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check the server configuration status.
        """
        config = await GuildConfig.objects.aget_or_none(guild_id=interaction.guild_id)
        config_cmd = self.channel.extras.get("mention", "`/config channel`")
        embed = discord.Embed(title=f"{settings.bot_name} configuration status", color=discord.Colour.blurple())

        if not config or not config.spawn_channel:
            embed.description = f"{settings.bot_name} is not configured in this server yet."
            embed.add_field(name="Channel", value=f"Not set - use {config_cmd}", inline=False)
            await interaction.response.send_message(embed=embed)
            return

        assert interaction.guild
        if interaction.guild.unavailable:
            await interaction.response.send_message("Your server is unavailable to the bot. Readding it may fix this.")
            return

        channel = interaction.guild.get_channel(config.spawn_channel)
        if not channel:
            embed.description = f"{settings.bot_name} is configured, but the specified channel could not be found."
            embed.add_field(name="Channel", value=f"Not found - use {config_cmd} to set it again", inline=False)
            await interaction.response.send_message(embed=embed)
            return

        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Status", value="Enabled" if config.enabled else "Disabled", inline=True)
        embed.add_field(name="Drop command", value="Enabled" if config.manual_drop_enabled else "Disabled", inline=True)

        def tick(granted: bool) -> str:
            return "\N{WHITE HEAVY CHECK MARK}" if granted else "\N{CROSS MARK}"

        channel_perms = channel.permissions_for(interaction.guild.me)
        checks = (
            ("Read Messages", channel_perms.read_messages),
            ("Send Messages", channel_perms.send_messages),
            ("Embed Links", channel_perms.embed_links),
            ("Attach Files", channel_perms.attach_files),
        )
        health_lines = "\n".join(f"{tick(granted)} {name}" for name, granted in checks)
        embed.add_field(name="Permissions", value=health_lines, inline=False)

        await interaction.response.send_message(embed=embed)
