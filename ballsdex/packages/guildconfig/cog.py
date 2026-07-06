from typing import TYPE_CHECKING, Optional, cast

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.translation import t
from ballsdex.core.utils.transformers import LanguageTransform
from bd_models.models import GuildConfig
from settings.models import settings

from .components import AcceptTOSView

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


def build_activation_embed() -> discord.Embed:
    # built per-call rather than as a module-level constant, since `t()` resolves the
    # current interaction's locale and must not be evaluated once at import time
    return discord.Embed(
        colour=0x00D936,
        title=t("{bot_name} activation").format(bot_name=settings.bot_name),
        description=t(
            "To enable {bot_name} in your server, you must "
            "read and accept the [Terms of Service]({tos_url}).\n\n"
            "As a summary, these are the rules of the bot:\n"
            "- No farming (spamming or creating servers for {collectibles})\n"
            "- Selling or exchanging {collectibles} "
            "against money or other goods is forbidden\n"
            "- Do not attempt to abuse the bot's internals\n"
            "**Not respecting these rules will lead to a blacklist**"
        ).format(
            bot_name=settings.bot_name, tos_url=settings.terms_of_service, collectibles=settings.plural_collectible_name
        ),
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
                    t("The current channel is not a valid text channel."), ephemeral=True
                )
                return

        guild = interaction.guild
        assert guild
        if guild.unavailable:
            await interaction.response.send_message(
                t(
                    "The server is unavailable to the bot and will not work properly. "
                    "Kicking and readding the bot may fix this."
                ),
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
                t(
                    "{bot_name} is missing the following permission(s) in {channel}: "
                    "**{perms}**. Please grant them, then try again."
                ).format(bot_name=settings.bot_name, channel=channel.mention, perms=", ".join(missing_perms)),
                ephemeral=True,
            )
            return

        view = AcceptTOSView(interaction, channel, user)
        embed = build_activation_embed()

        readable_channels = len([x for x in guild.text_channels if x.permissions_for(guild.me).read_messages])
        if readable_channels / len(guild.text_channels) < 0.75:
            embed.add_field(
                name=t("\N{WARNING SIGN}\N{VARIATION SELECTOR-16} Warning"),
                value=t(
                    "This server has {total} channels, but {bot_name} can only read {readable} channels.\n"
                    "Spawn is based on message activity, too few readable channels will result in "
                    "fewer spawns. It is recommended that you inspect your permissions."
                ).format(total=len(guild.text_channels), bot_name=settings.bot_name, readable=readable_channels),
            )
        message = await channel.send(embed=embed, view=view)
        view.message = message

        await interaction.response.send_message(
            t(
                "The activation embed has been sent in {channel}. Once accepted, "
                "{collectibles} will start spawning there based on message activity - "
                "send a few messages to trigger a test spawn."
            ).format(channel=channel.mention, collectibles=settings.plural_collectible_name),
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
                t(
                    "Spawning is now **disabled** in this server. Commands will still be "
                    "available, but the spawn of new {collectibles} "
                    "is suspended.\nTo re-enable the spawn, use the same command."
                ).format(collectibles=settings.plural_collectible_name)
            )
        else:
            config.enabled = True  # type: ignore
            await config.asave()
            self.bot.dispatch("ballsdex_settings_change", guild, enabled=True)
            if config.spawn_channel and (channel := guild.get_channel(config.spawn_channel)):
                if channel:
                    await interaction.response.send_message(
                        t(
                            "Spawning is now **enabled** in this server, {collectibles} will start "
                            "spawning soon in {channel}."
                        ).format(collectibles=settings.plural_collectible_name, channel=channel.mention)
                    )
                else:
                    await interaction.response.send_message(
                        t("The spawning channel specified in the configuration is not available."), ephemeral=True
                    )
            else:
                config_cmd = self.channel.extras.get("mention", "`/config channel`")
                await interaction.response.send_message(
                    t(
                        "Spawning is now **enabled** in this server, however there is no "
                        "spawning channel set. Please configure one with {config_cmd}."
                    ).format(config_cmd=config_cmd)
                )

    @app_commands.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def language(
        self, interaction: discord.Interaction["BallsDexBot"], language: Optional[LanguageTransform] = None
    ):
        """
        Set or reset the default language used to display countryballs in this server.

        Parameters
        ----------
        language: str
            The language to use, leave empty to reset to the bot's default language.
        """
        config, _ = await GuildConfig.objects.aget_or_create(guild_id=interaction.guild_id)
        config.language = language
        await config.asave(update_fields=("language",))
        if language:
            await interaction.response.send_message(
                t(
                    "{collectibles} will now be displayed in **{language}** "
                    "in this server, unless a player has set their own language."
                ).format(collectibles=settings.plural_collectible_name.title(), language=language),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                t(
                    "This server's language has been reset, {collectibles} will now be "
                    "displayed in the bot's default language (**{default_language}**), unless a player "
                    "has set their own language."
                ).format(collectibles=settings.plural_collectible_name, default_language=settings.default_language),
                ephemeral=True,
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
                t("Players can now use the drop command to manually spawn {collectibles}.").format(
                    collectibles=settings.plural_collectible_name
                )
            )
        else:
            await interaction.response.send_message(
                t("Players can no longer use the drop command to manually spawn {collectibles}.").format(
                    collectibles=settings.plural_collectible_name
                )
            )

    @app_commands.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check the server configuration status.
        """
        config = await GuildConfig.objects.aget_or_none(guild_id=interaction.guild_id)
        config_cmd = self.channel.extras.get("mention", "`/config channel`")
        embed = discord.Embed(
            title=t("{bot_name} configuration status").format(bot_name=settings.bot_name),
            color=discord.Colour.blurple(),
        )

        if not config or not config.spawn_channel:
            embed.description = t("{bot_name} is not configured in this server yet.").format(bot_name=settings.bot_name)
            embed.add_field(
                name=t("Channel"), value=t("Not set - use {config_cmd}").format(config_cmd=config_cmd), inline=False
            )
            await interaction.response.send_message(embed=embed)
            return

        assert interaction.guild
        if interaction.guild.unavailable:
            await interaction.response.send_message(
                t("Your server is unavailable to the bot. Readding it may fix this.")
            )
            return

        channel = interaction.guild.get_channel(config.spawn_channel)
        if not channel:
            embed.description = t("{bot_name} is configured, but the specified channel could not be found.").format(
                bot_name=settings.bot_name
            )
            embed.add_field(
                name=t("Channel"),
                value=t("Not found - use {config_cmd} to set it again").format(config_cmd=config_cmd),
                inline=False,
            )
            await interaction.response.send_message(embed=embed)
            return

        embed.add_field(name=t("Channel"), value=channel.mention, inline=True)
        embed.add_field(name=t("Status"), value=t("Enabled") if config.enabled else t("Disabled"), inline=True)
        embed.add_field(
            name=t("Drop command"), value=t("Enabled") if config.manual_drop_enabled else t("Disabled"), inline=True
        )

        def tick(granted: bool) -> str:
            return "\N{WHITE HEAVY CHECK MARK}" if granted else "\N{CROSS MARK}"

        channel_perms = channel.permissions_for(interaction.guild.me)
        checks = (
            (t("Read Messages"), channel_perms.read_messages),
            (t("Send Messages"), channel_perms.send_messages),
            (t("Embed Links"), channel_perms.embed_links),
            (t("Attach Files"), channel_perms.attach_files),
        )
        health_lines = "\n".join(f"{tick(granted)} {name}" for name, granted in checks)
        embed.add_field(name=t("Permissions"), value=health_lines, inline=False)

        await interaction.response.send_message(embed=embed)
