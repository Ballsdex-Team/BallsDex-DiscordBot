"""
Admin commands for managing user packs.
"""

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ballsdex.core.models import Player, UserPacks
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


@app_commands.default_permissions(administrator=True)
class PacksAdmin(app_commands.Group):
    """
    Admin commands for managing player packs.
    """

    def __init__(self):
        super().__init__(name="packs", description="Manage player packs")

    @app_commands.command(name="give")
    @app_commands.describe(
        user="The user to give packs to",
        pack_type="The type of pack to give",
        amount="The number of packs to give"
    )
    @app_commands.choices(pack_type=[
        app_commands.Choice(name="Common", value="common"),
        app_commands.Choice(name="Rare", value="rare"),
        app_commands.Choice(name="Epic", value="epic"),
    ])
    async def give_pack(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
        pack_type: app_commands.Choice[str],
        amount: int = 1,
    ):
        """
        Give packs to a user.

        Parameters
        ----------
        user: discord.User
            The user to give packs to
        pack_type: str
            The type of pack (common, rare, or epic)
        amount: int
            The number of packs to give (default: 1)
        """
        if amount <= 0:
            await interaction.response.send_message(
                "Amount must be a positive number.",
                ephemeral=True,
            )
            return

        if amount > 100:
            await interaction.response.send_message(
                "Cannot give more than 100 packs at once.",
                ephemeral=True,
            )
            return

        player, _ = await Player.get_or_create(discord_id=user.id)
        user_packs = await UserPacks.get_or_create_for_player(player)

        pack_name = pack_type.value
        field_name = f"{pack_name}_packs"
        current_count = getattr(user_packs, field_name, 0)
        setattr(user_packs, field_name, current_count + amount)
        await user_packs.save()

        pack_emoji = {"common": "⚪", "rare": "💙", "epic": "💜"}
        emoji = pack_emoji.get(pack_name, "📦")

        await interaction.response.send_message(
            f"{emoji} Gave **{amount}x {pack_name.title()} Pack(s)** to {user.mention}!",
            ephemeral=True,
        )

    @app_commands.command(name="view")
    @app_commands.describe(user="The user whose pack inventory you want to view")
    async def view_packs(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
    ):
        """
        View a user's pack inventory.

        Parameters
        ----------
        user: discord.User
            The user whose inventory you want to view
        """
        player = await Player.get_or_none(discord_id=user.id)
        if not player:
            await interaction.response.send_message(
                f"{user.mention} has no pack inventory.",
                ephemeral=True,
            )
            return

        user_packs = await UserPacks.get_or_none(player=player)
        if not user_packs:
            await interaction.response.send_message(
                f"{user.mention} has no packs.",
                ephemeral=True,
            )
            return

        total = user_packs.common_packs + user_packs.rare_packs + user_packs.epic_packs

        embed = discord.Embed(
            title=f"📦 {user.display_name}'s Packs",
            description=f"**{total}** packs total",
            color=0x3498DB,
        )
        embed.add_field(name="⚪ Common", value=str(user_packs.common_packs), inline=True)
        embed.add_field(name="💙 Rare", value=str(user_packs.rare_packs), inline=True)
        embed.add_field(name="💜 Epic", value=str(user_packs.epic_packs), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="remove")
    @app_commands.describe(
        user="The user to remove packs from",
        pack_type="The type of pack to remove",
        amount="The number of packs to remove"
    )
    @app_commands.choices(pack_type=[
        app_commands.Choice(name="Common", value="common"),
        app_commands.Choice(name="Rare", value="rare"),
        app_commands.Choice(name="Epic", value="epic"),
    ])
    async def remove_pack(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
        pack_type: app_commands.Choice[str],
        amount: int = 1,
    ):
        """
        Remove packs from a user.

        Parameters
        ----------
        user: discord.User
            The user to remove packs from
        pack_type: str
            The type of pack (common, rare, or epic)
        amount: int
            The number of packs to remove (default: 1)
        """
        if amount <= 0:
            await interaction.response.send_message(
                "Amount must be a positive number.",
                ephemeral=True,
            )
            return

        player = await Player.get_or_none(discord_id=user.id)
        if not player:
            await interaction.response.send_message(
                f"{user.mention} has no packs.",
                ephemeral=True,
            )
            return

        user_packs = await UserPacks.get_or_none(player=player)
        if not user_packs:
            await interaction.response.send_message(
                f"{user.mention} has no packs.",
                ephemeral=True,
            )
            return

        pack_name = pack_type.value
        field_name = f"{pack_name}_packs"
        current_count = getattr(user_packs, field_name, 0)
        new_count = max(0, current_count - amount)
        removed = current_count - new_count
        setattr(user_packs, field_name, new_count)
        await user_packs.save()

        await interaction.response.send_message(
            f"Removed **{removed}x {pack_name.title()} Pack(s)** from {user.mention}.",
            ephemeral=True,
        )
