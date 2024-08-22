from typing import TYPE_CHECKING, Optional, cast

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.models import GuildConfig, Player
from ballsdex.packages.config.components import AcceptTOSView
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

activation_embed = discord.Embed(
    colour=0x00D936,
    title=f"{settings.bot_name} activation",
    description=f"To enable {settings.bot_name} in your server, you must "
    f"read and accept the [Terms of Service]({settings.terms_of_service}).\n\n"
    "As a summary, these are the rules of the bot:\n"
    f"- No farming (spamming or creating servers for {settings.collectible_name}s)\n"
    f"- Selling or exchanging {settings.collectible_name}s "
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
    @app_commands.checks.bot_has_permissions(
        read_messages=True,
        send_messages=True,
        embed_links=True,
    )
    async def channel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        """
        The new text channel to set.

        Parameters
        ----------
        channel: discord.TextChannel
            The channel you want to set, current one if not specified.
        """
        user = cast(discord.Member, interaction.user)

        if not channel:
            channel = interaction.channel

        if not user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the permission to manage the server to use this."
            )
            return

        if channel and isinstance(channel, discord.TextChannel):
            view = AcceptTOSView(interaction, channel, user)
            message = await channel.send(embed=activation_embed, view=view)
            view.message = message

            await interaction.response.send_message(
                f"Embed sent in {channel.mention}.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "The specified channel is not valid.", ephemeral=True
            )

    @app_commands.command()
    async def disable(self, interaction: discord.Interaction):
        """
        Disable or enable countryballs spawning.
        """
        guild = cast(discord.Guild, interaction.guild)  # guild-only command
        user = cast(discord.Member, interaction.user)
        if not user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the permission to manage the server to use this."
            )
            return
        config, created = await GuildConfig.get_or_create(guild_id=interaction.guild_id)
        if config.enabled:
            config.enabled = False  # type: ignore
            await config.save()
            self.bot.dispatch("ballsdex_settings_change", guild, enabled=False)
            await interaction.response.send_message(
                f"{settings.bot_name} is now disabled in this server. Commands will still be "
                f"available, but the spawn of new {settings.collectible_name}s is suspended.\n"
                "To re-enable the spawn, use the same command."
            )
        else:
            config.enabled = True  # type: ignore
            await config.save()
            self.bot.dispatch("ballsdex_settings_change", guild, enabled=True)
            if config.spawn_channel and (channel := guild.get_channel(config.spawn_channel)):
                if channel:
                    await interaction.response.send_message(
                        f"{settings.bot_name} is now enabled in this server, "
                        f"{settings.collectible_name}s will start spawning "
                        f"soon in {channel.mention}."
                    )
                else:
                    await interaction.response.send_message(
                        "The spawning channel specified in the configuration is not available.",
                        ephemeral=True,
                    )
            else:
                await interaction.response.send_message(
                    f"{settings.bot_name} is now enabled in this server, however there is no "
                    "spawning channel set. Please configure one with `/config channel`."
                )
