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
                else random.randint(-settings.max_attack_bonus, settings.max_attack_bonus)
            ),
            health_bonus=(
                health_bonus
                if health_bonus is not None
                else random.randint(-settings.max_health_bonus, settings.max_health_bonus)
            ),
            special=special,
        )
        await interaction.followup.send(
            f"`{countryball.country}` {settings.collectible_name} was successfully given to "
            f"`{user}`.\nSpecial: `{special.name if special else None}` • ATK: "
            f"`{instance.attack_bonus:+d}` • HP:`{instance.health_bonus:+d}` "
        )
        await log_action(
            f"{interaction.user} gave {settings.collectible_name} "
            f"{countryball.country} to {user}. (Special={special.name if special else None} "
            f"ATK={instance.attack_bonus:+d} HP={instance.health_bonus:+d}).",
            interaction.client,
        )

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def giveall(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User,
        special: SpecialTransform | None = None,
        health_bonus: int | None = None,
        attack_bonus: int | None = None,
    ):
        """
        Give every ball from the database to a player.

        Parameters
        ----------
        user: discord.User
            The user to give all balls to
        special: Special | None
            Force all balls to have a special attribute when given. Random if not specified.
        health_bonus: int | None
            Force all balls to have a specific health bonus. Random if not specified.
        attack_bonus: int | None
            Force all balls to have a specific attack bonus. Random if not specified.
        """
        # the transformer triggered a response, meaning user tried an incorrect input
        if interaction.response.is_done():
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # Get all balls from database
            all_balls = await Ball.all()
            total_balls = len(all_balls)
            
            if total_balls == 0:
                await interaction.followup.send(
                    f"No {settings.plural_collectible_name} found in the database.",
                    ephemeral=True
                )
                return

            # Get or create player
            player, created = await Player.get_or_create(discord_id=user.id)
            
            given_count = 0
            failed_count = 0

            # Progress tracking function
            async def update_progress():
                while given_count + failed_count < total_balls:
                    progress = round(((given_count + failed_count) / total_balls) * 100)
                    try:
                        await interaction.followup.edit_message(
                            "@original",  # type: ignore
                            content=f"Giving all {settings.plural_collectible_name} to {user.mention}...\n"
                            f"Progress: {given_count + failed_count}/{total_balls} ({progress}%)\n"
                            f"✅ Successfully given: {given_count}\n"
                            f"❌ Failed: {failed_count}",
                        )
                    except discord.NotFound:
                        break
                    await asyncio.sleep(2)

            # Start progress tracking
            progress_task = asyncio.create_task(update_progress())

            try:
                # Give each ball to the user
                for ball in all_balls:
                    try:
                        await BallInstance.create(
                            ball=ball,
                            player=player,
                            attack_bonus=(
                                attack_bonus
                                if attack_bonus is not None
                                else random.randint(-settings.max_attack_bonus, settings.max_attack_bonus)
                            ),
                            health_bonus=(
                                health_bonus
                                if health_bonus is not None
                                else random.randint(-settings.max_health_bonus, settings.max_health_bonus)
                            ),
                            special=special,
                        )
                        given_count += 1
                    except Exception as e:
                        log.error(f"Failed to give ball {ball.country} to {user}: {e}")
                        failed_count += 1

                # Cancel progress tracking
                progress_task.cancel()

                # Final summary
                await interaction.followup.edit_message(
                    "@original",  # type: ignore
                    content=f"✅ **Giveall Complete!**\n\n"
                    f"Gave {given_count}/{total_balls} {settings.plural_collectible_name} to {user.mention}\n"
                    f"✅ **Successfully given:** {given_count}\n"
                    f"❌ **Failed:** {failed_count}"
                    + (f"\n\n**Special:** {special.name}" if special else "")
                    + (f"\n**Attack Bonus:** {attack_bonus:+d}" if attack_bonus is not None else "")
                    + (f"\n**Health Bonus:** {health_bonus:+d}" if health_bonus is not None else ""),
                )

                # Log the action
                await log_action(
                    f"{interaction.user} gave all {settings.plural_collectible_name} to {user}. "
                    f"({given_count} successful, {failed_count} failed) "
                    f"(Special={special.name if special else None} "
                    f"ATK={attack_bonus or 'random'} HP={health_bonus or 'random'}).",
                    interaction.client,
                )

            except Exception as e:
                progress_task.cancel()
                log.error(f"Error during giveall operation: {e}")
                await interaction.followup.edit_message(
                    "@original",  # type: ignore
                    content=f"❌ An error occurred during the giveall operation.\n"
                    f"Successfully gave: {given_count}\n"
                    f"Failed: {failed_count + 1}",
                )

        except Exception as e:
            log.error(f"Error in giveall command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while processing the giveall command.",
                ephemeral=True
            )

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def delete(
        self,
        interaction: discord.Interaction[BallsDexBot],
        ball_id: str,
    ):
        """
        Delete a specific ball instance from a user.

        Parameters
        ----------
        ball_id: str
            The ID of the ball instance to delete (use format: player_id:position)
        """
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # Parse ball_id (expecting format like "player_id:position" or just "instance_id")
            if ":" in ball_id:
                try:
                    player_id, position = ball_id.split(":", 1)
                    player_id = int(player_id)
                    position = int(position)
                    
                    # Get player
                    try:
                        player = await Player.get(discord_id=player_id)
                    except DoesNotExist:
                        await interaction.followup.send(
                            f"❌ Player with ID {player_id} not found.",
                            ephemeral=True
                        )
                        return
                    
                    # Get ball instances for this player
                    instances = await BallInstance.filter(player=player).order_by("id")
                    
                    if position < 1 or position > len(instances):
                        await interaction.followup.send(
                            f"❌ Invalid position. Player has {len(instances)} {settings.plural_collectible_name}.",
                            ephemeral=True
                        )
                        return
                    
                    instance = instances[position - 1]
                    
                except ValueError:
                    await interaction.followup.send(
                        "❌ Invalid ball ID format. Use `player_id:position` or `instance_id`.",
                        ephemeral=True
                    )
                    return
            else:
                # Direct instance ID
                try:
                    instance_id = int(ball_id)
                    instance = await BallInstance.get(id=instance_id).prefetch_related("ball", "player")
                except (ValueError, DoesNotExist):
                    await interaction.followup.send(
                        f"❌ Ball instance with ID {ball_id} not found.",
                        ephemeral=True
                    )
                    return

            # Store info for logging before deletion
            ball_name = instance.ball.country
            player_id = instance.player.discord_id
            instance_id = instance.id

            # Confirm deletion
            embed = discord.Embed(
                title="⚠️ Confirm Deletion",
                description=f"Are you sure you want to delete this {settings.collectible_name}?",
                color=0xff6b6b
            )
            embed.add_field(
                name="Ball Details",
                value=f"**Country:** {ball_name}\n"
                      f"**Instance ID:** {instance_id}\n"
                      f"**Owner:** <@{player_id}>\n"
                      f"**Special:** {instance.special.name if instance.special else 'None'}\n"
                      f"**ATK:** {instance.attack_bonus:+d}\n"
                      f"**HP:** {instance.health_bonus:+d}",
                inline=False
            )

            view = ConfirmChoiceView(interaction.user.id)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            await view.wait()

            if view.value is None:
                await interaction.edit_original_response(
                    content="⏰ Deletion timed out.", embed=None, view=None
                )
                return
            elif not view.value:
                await interaction.edit_original_response(
                    content="❌ Deletion cancelled.", embed=None, view=None
                )
                return

            # Delete the instance
            await instance.delete()

            await interaction.edit_original_response(
                content=f"✅ Successfully deleted {settings.collectible_name} "
                        f"**{ball_name}** (ID: {instance_id}) from <@{player_id}>.",
                embed=None,
                view=None
            )

            # Log the action
            await log_action(
                f"{interaction.user} deleted {settings.collectible_name} "
                f"{ball_name} (ID: {instance_id}) from player {player_id}.",
                interaction.client,
            )

        except Exception as e:
            log.error(f"Error in delete command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while deleting the ball instance.",
                ephemeral=True
            )

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def info(
        self,
        interaction: discord.Interaction[BallsDexBot],
        ball: BallTransform,
    ):
        """
        Get information about a specific ball.

        Parameters
        ----------
        ball: Ball
            The ball to get information about
        """
        # the transformer triggered a response, meaning user tried an incorrect input
        if interaction.response.is_done():
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # Get total instances of this ball
            total_instances = await BallInstance.filter(ball=ball).count()
            
            # Get players who own this ball
            players_with_ball = await BallInstance.filter(ball=ball).prefetch_related("player").distinct().values_list("player__discord_id", flat=True)
            unique_owners = len(set(players_with_ball))

            embed = discord.Embed(
                title=f"🏴󠁣󠁭󠁥󠁮󠁿 {ball.country} Information",
                color=0x3498db
            )
            
            embed.add_field(
                name="Basic Info",
                value=f"**Country:** {ball.country}\n"
                      f"**Rarity:** {ball.rarity:.1%}\n"
                      f"**Enabled:** {'✅' if ball.enabled else '❌'}",
                inline=True
            )
            
            embed.add_field(
                name="Collection Stats",
                value=f"**Total Instances:** {total_instances}\n"
                      f"**Unique Owners:** {unique_owners}",
                inline=True
            )

            # Add ball image if available
            if hasattr(ball, 'wild_card') and ball.wild_card:
                embed.set_thumbnail(url=ball.wild_card)
            elif hasattr(ball, 'collection_card') and ball.collection_card:
                embed.set_thumbnail(url=ball.collection_card)

            # Get some recent instances for additional info
            recent_instances = await BallInstance.filter(ball=ball).prefetch_related("special").order_by("-id").limit(5)
            
            if recent_instances:
                recent_info = []
                for instance in recent_instances:
                    special_name = instance.special.name if instance.special else "None"
                    recent_info.append(
                        f"ID {instance.id}: Special={special_name}, ATK={instance.attack_bonus:+d}, HP={instance.health_bonus:+d}"
                    )
                
                embed.add_field(
                    name="Recent Instances",
                    value="\n".join(recent_info),
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            log.error(f"Error in info command: {e}")
            await interaction.followup.send(
                f"❌ An error occurred while getting information about {ball.country}.",
                ephemeral=True
            )

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def count(self, interaction: discord.Interaction[BallsDexBot]):
        """
        Show statistics about the bot's ball collection.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # Get various statistics
            total_balls = await Ball.all().count()
            enabled_balls = await Ball.filter(enabled=True).count()
            total_instances = await BallInstance.all().count()
            total_players = await Player.all().count()
            
            # Get rarity distribution
            rarity_ranges = [
                ("Very Common", 0.8, 1.0),
                ("Common", 0.4, 0.8),
                ("Uncommon", 0.2, 0.4),
                ("Rare", 0.05, 0.2),
                ("Very Rare", 0.01, 0.05),
                ("Ultra Rare", 0.0, 0.01),
            ]
            
            rarity_counts = {}
            for name, min_rarity, max_rarity in rarity_ranges:
                count = await Ball.filter(rarity__gte=min_rarity, rarity__lt=max_rarity).count()
                rarity_counts[name] = count

            embed = discord.Embed(
                title=f"📊 {settings.collectible_name.title()} Statistics",
                color=0x2ecc71
            )
            
            embed.add_field(
                name="General Stats",
                value=f"**Total {settings.plural_collectible_name.title()}:** {total_balls}\n"
                      f"**Enabled:** {enabled_balls}\n"
                      f"**Disabled:** {total_balls - enabled_balls}\n"
                      f"**Total Instances:** {total_instances}\n"
                      f"**Total Players:** {total_players}",
                inline=False
            )
            
            rarity_text = "\n".join([f"**{name}:** {count}" for name, count in rarity_counts.items() if count > 0])
            if rarity_text:
                embed.add_field(
                    name="Rarity Distribution",
                    value=rarity_text,
                    inline=False
                )

            # Calculate average instances per player
            if total_players > 0:
                avg_per_player = total_instances / total_players
                embed.add_field(
                    name="Additional Info",
                    value=f"**Average per Player:** {avg_per_player:.1f}",
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            log.error(f"Error in count command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while gathering statistics.",
                ephemeral=True
            )
