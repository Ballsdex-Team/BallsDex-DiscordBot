import datetime

import discord
from discord import app_commands
from discord.utils import format_dt

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.models import BallInstance, GuildConfig, Player
from ballsdex.core.utils.enums import (
    DONATION_POLICY_MAP,
    FRIEND_POLICY_MAP,
    MENTION_POLICY_MAP,
    PRIVATE_POLICY_MAP,
)
from ballsdex.core.utils.enums import TRADE_COOLDOWN_POLICY_MAP as TRADE_POLICY_MAP
from ballsdex.settings import settings

class PlayerInfoView(discord.ui.View):
    def __init__(self, player: Player, username: str):
        super().__init__()
        self.player = player
        self.username = username
    @discord.ui.button(label="Recent Catches", style=discord.ButtonStyle.primary)
    async def recently_caught(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Display the last 10 catches of the user, and how long it took for each catch
        recent_balls = await BallInstance.filter(
            player=self.player,
        ).order_by("-catch_date").limit(10)
        embed = discord.Embed(title=f"Last {len(recent_balls)} catches for {self.username}")
        for ball in recent_balls:
            catch_time = int((ball.catch_date - ball.spawned_time).total_seconds())
            embed.add_field(name=ball.description(short=True),value=f"{catch_time//60}:{catch_time%60:02} in {ball.server_id}",inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class Info(app_commands.Group):
    """
    Information Commands
    """

    @app_commands.command()
    async def guild(
        self,
        interaction: discord.Interaction[BallsDexBot],
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
            The amount of days to look back for the amount of countryballs caught.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.client.get_guild(int(guild_id))

        if not guild:
            try:
                guild = await interaction.client.fetch_guild(int(guild_id))  # type: ignore
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

        url = None
        if config := await GuildConfig.get_or_none(guild_id=guild.id):
            spawn_enabled = config.enabled and config.guild_id
            if settings.admin_url:
                url = f"{settings.admin_url}/bd_models/guildconfig/{config.pk}/change/"
        else:
            spawn_enabled = False

        total_server_balls = await BallInstance.filter(
            catch_date__gte=datetime.datetime.now() - datetime.timedelta(days=days),
            server_id=guild.id,
        ).prefetch_related("player")
        if guild.owner_id:
            owner = await interaction.client.fetch_user(guild.owner_id)
            embed = discord.Embed(
                title=f"{guild.name} ({guild.id})",
                url=url,
                description=f"**Owner:** {owner} ({guild.owner_id})",
                color=discord.Color.blurple(),
            )
        else:
            embed = discord.Embed(
                title=f"{guild.name} ({guild.id})",
                url=url,
                color=discord.Color.blurple(),
            )
        embed.add_field(name="Members:", value=guild.member_count)
        embed.add_field(name="Spawn enabled:", value=spawn_enabled)
        embed.add_field(name="Created at:", value=format_dt(guild.created_at, style="F"))
        embed.add_field(
            name=f"{settings.plural_collectible_name.title()} caught ({days} days):",
            value=len(total_server_balls),
        )
        embed.add_field(
            name=f"Amount of users who caught\n{settings.plural_collectible_name} ({days} days):",
            value=len(set([x.player.discord_id for x in total_server_balls])),
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command()
    async def user(
        self,
        interaction: discord.Interaction[BallsDexBot],
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
            The amount of days to look back for the amount of countryballs caught.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        player = await Player.get_or_none(discord_id=user.id)
        if not player:
            await interaction.followup.send("The user you gave does not exist.", ephemeral=True)
            return
        url = (
            f"{settings.admin_url}/bd_models/player/{player.pk}/change/"
            if settings.admin_url
            else None
        )
        total_user_balls = await BallInstance.filter(
            catch_date__gte=datetime.datetime.now() - datetime.timedelta(days=days),
            player=player,
        )
        embed = discord.Embed(
            title=f"{user} ({user.id})",
            url=url,
            description=(
                f"**Privacy Policy:** {PRIVATE_POLICY_MAP[player.privacy_policy]}\n"
                f"**Donation Policy:** {DONATION_POLICY_MAP[player.donation_policy]}\n"
                f"**Mention Policy:** {MENTION_POLICY_MAP[player.mention_policy]}\n"
                f"**Friend Policy:** {FRIEND_POLICY_MAP[player.friend_policy]}\n"
                f"**Trade Cooldown Policy:** {TRADE_POLICY_MAP[player.trade_cooldown_policy]}\n"
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name=f"{settings.plural_collectible_name.title()} caught ({days} days):",
            value=len(total_user_balls),
        )
        embed.add_field(
            name=f"Unique {settings.plural_collectible_name} caught ({days} days):",
            value=len(set([ball.countryball for ball in total_user_balls])),
        )
        embed.add_field(
            name=f"Total servers with {settings.plural_collectible_name} caught ({days} days):",
            value=len(set([x.server_id for x in total_user_balls])),
        )
        embed.add_field(
            name=f"Total {settings.plural_collectible_name} caught:",
            value=await BallInstance.filter(player__discord_id=user.id).count(),
        )
        embed.add_field(
            name=f"Total unique {settings.plural_collectible_name} caught:",
            value=len(set([x.countryball for x in total_user_balls])),
        )
        embed.add_field(
            name=f"Total servers with {settings.plural_collectible_name} caught:",
            value=len(set([x.server_id for x in total_user_balls])),
        )
        embed.set_thumbnail(url=user.display_avatar)  # type: ignore
        await interaction.followup.send(embed=embed, ephemeral=True, view=PlayerInfoView(player,user.name))
