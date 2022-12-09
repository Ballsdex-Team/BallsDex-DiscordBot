import discord

from typing import TYPE_CHECKING, cast

from discord import app_commands
from discord.ext import commands
from ballsdex.core.models import GuildConfig

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


@app_commands.default_permissions(manage_guild=True)
@app_commands.guild_only()
class Config(commands.GroupCog):
    """
    View and manage your countryballs collection.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.describe(channel="The new text channel to set.")
    async def channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        """
        Set or change the channel where countryballs will spawn.
        """
        guild = cast(discord.Guild, interaction.guild)  # guild-only command
        user = cast(discord.Member, interaction.user)
        if not user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the permission to manage the server to use this."
            )
            return
        config, created = await GuildConfig.get_or_create(guild_id=interaction.guild_id)
        if not channel.permissions_for(guild.me).read_messages:
            await interaction.response.send_message(
                f"I need the permission to read messages in {channel.mention}."
            )
            return
        if not channel.permissions_for(guild.me).send_messages:
            await interaction.response.send_message(
                f"I need the permission to send messages in {channel.mention}."
            )
            return
        if not channel.permissions_for(guild.me).embed_links:
            await interaction.response.send_message(
                f"I need the permission to send embed links in {channel.mention}."
            )
            return
        config.spawn_channel = channel.id  # type: ignore
        await config.save()
        self.bot.dispatch("ballsdex_settings_change", guild, channel=channel)
        await interaction.response.send_message(
            f"The new spawn channel was successfully set to {channel.mention}.\n"
            "Balls will start spawning as users talk unless the bot is disabled."
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
                "BallsDex is now disabled in this server. Commands will still be available, but "
                "the spawn of new countryballs is suspended.\n"
                "To re-enable the spawn, use the same command."
            )
        else:
            config.enabled = True  # type: ignore
            await config.save()
            self.bot.dispatch("ballsdex_settings_change", guild, enabled=True)
            if config.spawn_channel and (channel := guild.get_channel(config.spawn_channel)):
                await interaction.response.send_message(
                    "BallsDex is now enabled in this server, countryballs will start spawning "
                    f"soon in {channel.mention}."
                )
            else:
                await interaction.response.send_message(
                    "BallsDex is now enabled in this server, however there is no spawning "
                    "channel set. Please configure one with `/config channel`."
                )
