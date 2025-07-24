import asyncio
import logging
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.utils import format_dt
from tortoise.exceptions import BaseORMException, DoesNotExist

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.models import Ball, BallInstance, Player, Special, Trade, TradeObject
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.logging import log_action
from ballsdex.core.utils.transformers import (
    BallTransform,
    EconomyTransform,
    RegimeTransform,
    SpecialTransform,
)
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.packages.countryballs.cog import CountryBallsSpawner
    from ballsdex.packages.countryballs.countryball import BallSpawnView

log = logging.getLogger("ballsdex.packages.admin.balls")
FILENAME_RE = re.compile(r"^(.+)(\.\S+)$")


async def save_file(attachment: discord.Attachment) -> Path:
    path = Path(f"./admin_panel/media/{attachment.filename}")
    match = FILENAME_RE.match(attachment.filename)
    if not match:
        raise TypeError("The file you uploaded lacks an extension.")
    i = 1
    while path.exists():
        path = Path(f"./admin_panel/media/{match.group(1)}-{i}{match.group(2)}")
        i = i + 1
    await attachment.save(path)
    return path.relative_to("./admin_panel/media/")


class BallDropView(discord.ui.View):
    """
    View for handling ball drop claims with a button.
    """
    
    def __init__(self, ball: Ball, special: Special | None = None, 
                 atk_bonus: int | None = None, hp_bonus: int | None = None):
        super().__init__(timeout=300.0)  # 5 minute timeout
        self.ball = ball
        self.special = special
        self.atk_bonus = atk_bonus
        self.hp_bonus = hp_bonus
        self.claimed = False
        self.claimer = None
        
    @discord.ui.button(label="🏃 Claim!", style=discord.ButtonStyle.primary, emoji="⚡")
    async def claim_ball(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle ball claiming when button is clicked."""
        if self.claimed:
            await interaction.response.send_message(
                f"This {settings.collectible_name} has already been claimed by {self.claimer.mention}!",
                ephemeral=True
            )
            return
            
        # Mark as claimed immediately to prevent race conditions
        self.claimed = True
        self.claimer = interaction.user
        
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get or create player
            player, created = await Player.get_or_create(discord_id=interaction.user.id)
            
            # Create ball instance with specified or random bonuses
            instance = await BallInstance.create(
                ball=self.ball,
                player=player,
                attack_bonus=(
                    self.atk_bonus
                    if self.atk_bonus is not None
                    else random.randint(-settings.max_attack_bonus, settings.max_attack_bonus)
                ),
                health_bonus=(
                    self.hp_bonus
                    if self.hp_bonus is not None
                    else random.randint(-settings.max_health_bonus, settings.max_health_bonus)
                ),
                special=self.special,
            )
            
            # Disable the button and update the embed
            button.disabled = True
            button.label = f"Claimed by {interaction.user.display_name}!"
            button.style = discord.ButtonStyle.success
            
            # Create success embed
            embed = discord.Embed(
                title=f"{settings.collectible_name.title()} Claimed!",
                description=f"🎉 {interaction.user.mention} claimed the **{self.ball.country}** {settings.collectible_name}!",
                color=0x00ff00
            )
            embed.add_field(
                name="Ball Details",
                value=f"**Special:** {self.special.name if self.special else 'None'}\n"
                      f"**Attack Bonus:** {instance.attack_bonus:+d}\n"
                      f"**Health Bonus:** {instance.health_bonus:+d}",
                inline=False
            )
            
            if hasattr(self.ball, 'wild_card') and self.ball.wild_card:
                embed.set_image(url=self.ball.wild_card)
            elif hasattr(self.ball, 'collection_card') and self.ball.collection_card:
                embed.set_image(url=self.ball.collection_card)
                
            # Update the original message
            await interaction.edit_original_response(embed=embed, view=self)
            
            # Send confirmation to claimer
            await interaction.followup.send(
                f"🎉 Congratulations! You claimed the **{self.ball.country}** {settings.collectible_name}!\n"
                f"Special: `{self.special.name if self.special else 'None'}` • "
                f"ATK: `{instance.attack_bonus:+d}` • HP: `{instance.health_bonus:+d}`",
                ephemeral=True
            )
            
            # Log the action
            await log_action(
                f"{interaction.user} claimed dropped {settings.collectible_name} "
                f"{self.ball.country} in {interaction.channel}. "
                f"(Special={self.special.name if self.special else None} "
                f"ATK={instance.attack_bonus:+d} HP={instance.health_bonus:+d}).",
                interaction.client,
            )
            
        except Exception as e:
            # Reset claimed status on error
            self.claimed = False
            self.claimer = None
            log.error(f"Error creating ball instance: {e}")
            
            await interaction.followup.send(
                f"❌ An error occurred while claiming the {settings.collectible_name}. Please try again.",
                ephemeral=True
            )
            
    async def on_timeout(self):
        """Handle view timeout - disable the button."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
                if not self.claimed:
                    item.label = "⏰ Expired"
                    item.style = discord.ButtonStyle.secondary


class Balls(app_commands.Group):
    """
    Countryballs management
    """

    async def _spawn_bomb(
        self,
        interaction: discord.Interaction[BallsDexBot],
        countryball_cls: type["BallSpawnView"],
        countryball: Ball | None,
        channel: discord.TextChannel,
        n: int,
        special: Special | None = None,
        atk_bonus: int | None = None,
        hp_bonus: int | None = None,
    ):
        spawned = 0

        async def update_message_loop():
            for i in range(5 * 12 * 10):  # timeout progress after 10 minutes
                await interaction.followup.edit_message(
                    "@original",  # type: ignore
                    content=f"Spawn bomb in progress in {channel.mention}, "
                    f"{settings.collectible_name.title()}: {countryball or 'Random'}\n"
                    f"{spawned}/{n} spawned ({round((spawned / n) * 100)}%)",
                )
                await asyncio.sleep(5)
            await interaction.followup.edit_message(
                "@original", content="Spawn bomb seems to have timed out."  # type: ignore
            )

        await interaction.response.send_message(
            f"Starting spawn bomb in {channel.mention}...", ephemeral=True
        )
        task = interaction.client.loop.create_task(update_message_loop())
        try:
            for i in range(n):
                if not countryball:
                    ball = await countryball_cls.get_random(interaction.client)
                else:
                    ball = countryball_cls(interaction.client, countryball)
                ball.special = special
                ball.atk_bonus = atk_bonus
                ball.hp_bonus = hp_bonus
                result = await ball.spawn(channel)
                if not result:
                    task.cancel()
                    await interaction.followup.edit_message(
                        "@original",  # type: ignore
                        content=f"A {settings.collectible_name} failed to spawn, probably "
                        "indicating a lack of permissions to send messages "
                        f"or upload files in {channel.mention}.",
                    )
                    return
                spawned += 1
            task.cancel()
            await interaction.followup.edit_message(
                "@original",  # type: ignore
                content=f"Successfully spawned {spawned} {settings.plural_collectible_name} "
                f"in {channel.mention}!",
            )
        finally:
            task.cancel()

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def spawn(
        self,
        interaction: discord.Interaction[BallsDexBot],
        countryball: BallTransform | None = None,
        channel: discord.TextChannel | None = None,
        n: app_commands.Range[int, 1, 100] = 1,
        special: SpecialTransform | None = None,
        atk_bonus: int | None = None,
        hp_bonus: int | None = None,
    ):
        """
        Force spawn a random or specified countryball.

        Parameters
        ----------
        countryball: Ball | None
            The countryball you want to spawn. Random according to rarities if not specified.
        channel: discord.TextChannel | None
            The channel you want to spawn the countryball in. Current channel if not specified.
        n: int
            The number of countryballs to spawn. If no countryball was specified, it's random
            every time.
        special: Special | None
            Force the countryball to have a special attribute when caught.
        atk_bonus: int | None
            Force the countryball to have a specific attack bonus when caught.
        hp_bonus: int | None
            Force the countryball to have a specific health bonus when caught.
        """
        # the transformer triggered a response, meaning user tried an incorrect input
        if interaction.response.is_done():
            return
        cog = cast("CountryBallsSpawner | None", interaction.client.get_cog("CountryBallsSpawner"))
        if not cog:
            prefix = (
                settings.prefix
                if interaction.client.intents.message_content or not interaction.client.user
                else f"{interaction.client.user.mention} "
            )
            # do not replace `countryballs` with `settings.collectible_name`, it is intended
            await interaction.response.send_message(
                "The `countryballs` package is not loaded, this command is unavailable.\n"
                "Please resolve the errors preventing this package from loading. Use "
                f'"{prefix}reload countryballs" to try reloading it.',
                ephemeral=True,
            )
            return

        special_attrs = []
        if special is not None:
            special_attrs.append(f"special={special.name}")
        if atk_bonus is not None:
            special_attrs.append(f"atk={atk_bonus}")
        if hp_bonus is not None:
            special_attrs.append(f"hp={hp_bonus}")
        if n > 1:
            await self._spawn_bomb(
                interaction,
                cog.countryball_cls,
                countryball,
                channel or interaction.channel,  # type: ignore
                n,
                special,
                atk_bonus,
                hp_bonus,
            )
            await log_action(
                f"{interaction.user} spawned {settings.collectible_name}"
                f" {countryball or 'random'} {n} times in {channel or interaction.channel}"
                + (f" ({', '.join(special_attrs)})." if special_attrs else "."),
                interaction.client,
            )

            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        if not countryball:
            ball = await cog.countryball_cls.get_random(interaction.client)
        else:
            ball = cog.countryball_cls(interaction.client, countryball)
        ball.special = special
        ball.atk_bonus = atk_bonus
        ball.hp_bonus = hp_bonus
        result = await ball.spawn(channel or interaction.channel)  # type: ignore

        if result:
            await interaction.followup.send(
                f"{settings.collectible_name.title()} spawned.", ephemeral=True
            )
            await log_action(
                f"{interaction.user} spawned {settings.collectible_name} {ball.name} "
                f"in {channel or interaction.channel}"
                + (f" ({', '.join(special_attrs)})." if special_attrs else "."),
                interaction.client,
            )

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def drop(
        self,
        interaction: discord.Interaction[BallsDexBot],
        countryball: BallTransform | None = None,
        channel: discord.TextChannel | None = None,
        special: SpecialTransform | None = None,
        atk_bonus: int | None = None,
        hp_bonus: int | None = None,
    ):
        """
        Drop a countryball with a claim button for users to compete for.

        Parameters
        ----------
        countryball: Ball | None
            The countryball to drop. Random according to rarities if not specified.
        channel: discord.TextChannel | None
            The channel to drop the countryball in. Current channel if not specified.
        special: Special | None
            Force the countryball to have a special attribute when claimed.
        atk_bonus: int | None
            Force the countryball to have a specific attack bonus when claimed.
        hp_bonus: int | None
            Force the countryball to have a specific health bonus when claimed.
        """
        # the transformer triggered a response, meaning user tried an incorrect input
        if interaction.response.is_done():
            return
            
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Cannot drop balls in this type of channel.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # Get the ball to drop
            if not countryball:
                # Get random ball from database
                balls = await Ball.all()
                if not balls:
                    await interaction.followup.send(
                        f"❌ No {settings.plural_collectible_name} found in the database.",
                        ephemeral=True
                    )
                    return
                    
                # Select random ball based on rarity weights
                weights = [1 / ball.rarity for ball in balls]
                countryball = random.choices(balls, weights=weights, k=1)[0]

            # Create the drop embed
            embed = discord.Embed(
                title=f"🎁 {settings.collectible_name.title()} Drop!",
                description=f"A wild **{countryball.country}** {settings.collectible_name} has appeared!\n"
                           f"Click the button below to claim it!",
                color=0x3498db
            )
            
            embed.add_field(
                name="Ball Info",
                value=f"**Country:** {countryball.country}\n"
                      f"**Rarity:** {countryball.rarity:.1%}",
                inline=True
            )
            
            if special:
                embed.add_field(
                    name="Special",
                    value=f"🌟 {special.name}",
                    inline=True
                )
            
            bonuses = []
            if atk_bonus is not None:
                bonuses.append(f"ATK: {atk_bonus:+d}")
            if hp_bonus is not None:
                bonuses.append(f"HP: {hp_bonus:+d}")
            
            if bonuses:
                embed.add_field(
                    name="Forced Bonuses",
                    value=" • ".join(bonuses),
                    inline=True
                )
                
            embed.set_footer(text="⏰ This drop will expire in 5 minutes!")
            
            # Add ball image if available
            if hasattr(countryball, 'wild_card') and countryball.wild_card:
                embed.set_image(url=countryball.wild_card)
            elif hasattr(countryball, 'collection_card') and countryball.collection_card:
                embed.set_image(url=countryball.collection_card)

            # Create the view with claim button
            view = BallDropView(countryball, special, atk_bonus, hp_bonus)
            
            # Send the drop message
            drop_message = await target_channel.send(embed=embed, view=view)
            
            # Confirm to admin
            special_attrs = []
            if special is not None:
                special_attrs.append(f"special={special.name}")
            if atk_bonus is not None:
                special_attrs.append(f"atk={atk_bonus}")
            if hp_bonus is not None:
                special_attrs.append(f"hp={hp_bonus}")
                
            await interaction.followup.send(
                f"✅ {settings.collectible_name.title()} drop created in {target_channel.mention}!\n"
                f"**Ball:** {countryball.country}"
                + (f" ({', '.join(special_attrs)})" if special_attrs else ""),
                ephemeral=True
            )
            
            # Log the action
            await log_action(
                f"{interaction.user} created a {settings.collectible_name} drop "
                f"({countryball.country}) in {target_channel}"
                + (f" ({', '.join(special_attrs)})." if special_attrs else "."),
                interaction.client,
            )
            
        except Exception as e:
            log.error(f"Error creating ball drop: {e}")
            await interaction.followup.send(
                f"❌ An error occurred while creating the {settings.collectible_name} drop.",
                ephemeral=True
            )

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def give(
        self,
        interaction: discord.Interaction[BallsDexBot],
        countryball: BallTransform,
        user: discord.User,
        special: SpecialTransform | None = None,
        health_bonus: int | None = None,
        attack_bonus: int | None = None,
    ):
        """
        Give the specified countryball to a player.

        Parameters
        ----------
        countryball: Ball
        user: discord.User
        special: Special | None
        health_bonus: int | None
            Omit this to make it random.
        attack_bonus: int | None
            Omit this to make it random.
        """
        # the transformers triggered a response, meaning user tried an incorrect input
        if interaction.response.is_done():
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        player, created = await Player.get_or_create(discord_id=user.id)
        instance = await BallInstance.create(
            ball=countryball,
            player=player,
            attack_bonus=(
                attack_bonus
                if attack_bonus is not None
                else random.randint(-settings