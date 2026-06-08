from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.transformers import BallInstanceTransform
from ballsdex.packages.countryballs.countryball import BallSpawnView

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


@app_commands.command()
@app_commands.checks.cooldown(1, 240, key=lambda i: i.user.id)
async def drop(interaction: discord.Interaction["BallsDexBot"], countryball: BallInstanceTransform):
    """
    Drop a countryball from your inventory.

    Parameters
    ----------
    countryball: BallInstance
        The ball you want to drop
    """
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("This channel isn't a text channel.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    description = countryball.description(include_emoji=True, bot=interaction.client)
    view = ConfirmChoiceView(
        interaction, accept_message=f"Confirmed, dropping {description}...", cancel_message="Request cancelled."
    )
    await interaction.followup.send(f"Are you sure you want to drop {description}?", view=view, ephemeral=True)
    await view.wait()
    if not view.value:
        return

    ball_view = await BallSpawnView.from_existing(interaction.client, countryball)
    await ball_view.spawn(channel)
