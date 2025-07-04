import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import asyncio
from ballsdex.core.models import GuildConfig, BallInstance
from ballsdex.settings import settings
from ballsdex.core.utils.utils import is_staff
from datetime import datetime, timedelta, timezone
import traceback
import math
import logging
import io


logging.basicConfig(level=logging.ERROR) 
logger = logging.getLogger(__name__)

class Broadcast(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pages = {} 

    async def cog_load(self):
        """Runs when cog loads"""
        await self.bot.wait_until_ready()
        pass

    async def get_broadcast_channels(self):
        try:
            channels = set()
            async for config in GuildConfig.filter(enabled=True, spawn_channel__isnull=False):
                channel = self.bot.get_channel(config.spawn_channel)
                if channel:
                    channels.add(config.spawn_channel)
                else:
                    try:
                        config.enabled = False
                        await config.save()
                        logger.debug(f"Disabled guild {config.guild_id} due to missing channel {config.spawn_channel}")
                    except Exception as e:
                        logger.error(f"Error disabling guild {config.guild_id}: {str(e)}")
            return channels
        except Exception as e:
            logger.error(f"Error getting broadcast channels: {str(e)}")
            logger.error(traceback.format_exc())
            return set()

    async def get_member_count(self, guild):
        """to get the number of server members"""
        try:
            if not guild.me.guild_permissions.view_channel:
                logger.debug(f"No permission to view channel in guild {guild.name}")
                return 0
                
            return guild.member_count
                
        except Exception as e:
            logger.error(f"Error in get_member_count: {str(e)}")
            logger.error(traceback.format_exc())
            return 0

    def create_embed(self, channel_list, total_stats, page, total_pages):
        """create embed message"""
        try:
            embed = discord.Embed(
                title="Ball Generation Channel List",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(
                name="Statistics",
                value=(
                    f"Total Channels: {total_stats['total_channels']}\n"
                    f"Total Members: {total_stats['total_members']:,}\n"
                    f"Unknown Channels: {total_stats['unknown_channels']}\n"
                    f"Unknown Guilds: {total_stats['unknown_guilds']}"
                ),
                inline=False
            )
            
            for channel_info in channel_list:
                embed.add_field(
                    name=channel_info['name'],
                    value=channel_info['value'],
                    inline=False
                )
            
            embed.set_footer(text=f"Page {page}/{total_pages}")
            return embed
        except Exception as e:
            logger.error(f"Error creating embed: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    class PaginationView(discord.ui.View):
        def __init__(self, cog, channel_list, total_stats, timeout=180):
            super().__init__(timeout=timeout)
            self.cog = cog
            self.channel_list = channel_list
            self.total_stats = total_stats
            self.current_page = 1
            self.total_pages = math.ceil(len(channel_list) / 5)
            
            self.update_buttons()
            
        def update_buttons(self):
            self.previous_page.disabled = self.current_page <= 1
            self.next_page.disabled = self.current_page >= self.total_pages
            
        async def on_timeout(self):
            for item in self.children:
                item.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
            
        @discord.ui.button(label="Previous Page", style=discord.ButtonStyle.primary)
        async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.current_page > 1:
                self.current_page -= 1
                self.update_buttons()
                await self.update_message(interaction)
                
        @discord.ui.button(label="Next Page", style=discord.ButtonStyle.primary)
        async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.current_page < self.total_pages:
                self.current_page += 1
                self.update_buttons()
                await self.update_message(interaction)
                
        async def update_message(self, interaction: discord.Interaction):
            start_idx = (self.current_page - 1) * 5
            end_idx = start_idx + 5
            current_channels = self.channel_list[start_idx:end_idx]
            
            embed = self.cog.create_embed(current_channels, self.total_stats, self.current_page, self.total_pages)
            await interaction.response.edit_message(embed=embed, view=self)
            self.message = await interaction.original_response()

    @app_commands.command(name="list_broadcast_channels", description="List all ball spawn channels")
    @app_commands.default_permissions(administrator=True)
    async def list_broadcast_channels(self, interaction: discord.Interaction):
        if not is_staff(interaction):
            await interaction.response.send_message("You need bot admin permissions to use this command.")
            return

        try:
            channels = await self.get_broadcast_channels()
            if not channels:
                await interaction.response.send_message("No ball spawn channels are currently configured.")
                return

            await interaction.response.send_message("Collecting server information, please wait...")
            
            channel_list = []
            total_stats = {
                'total_channels': len(channels),
                'total_members': 0,
                'unknown_channels': 0,
                'unknown_guilds': 0
            }
            
            for channel_id in channels:
                try:
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        total_stats['unknown_channels'] += 1
                        continue
                        
                    guild = channel.guild
                    if not guild:
                        total_stats['unknown_guilds'] += 1
                        continue
                        
                    member_count = await self.get_member_count(guild)
                    total_stats['total_members'] += member_count
                    
                    channel_list.append({
                        'name': f"**{guild.name}**",
                        'value': (
                            f"└ Channel: #{channel.name} (`{channel.id}`)\n"
                            f"└ Guild ID: `{guild.id}`\n"
                            f"└ Members: {member_count:,}"
                        )
                    })

                    total_catches = await BallInstance.filter(server_id=guild.id).count()
                    if total_catches >= 20: 
                        recent_catches = await BallInstance.filter(
                            server_id=guild.id
                        ).order_by("-catch_date").limit(10).prefetch_related("player")

                        if recent_catches:
                            unique_catchers = len(set(ball.player.discord_id for ball in recent_catches))
                            if unique_catchers == 1:
                                player = recent_catches[0].player
                                channel_list[-1]['value'] += f"\n└ ⚠️ **The last 10 balls were all caught by {player}**"

                except Exception as e:
                    logger.error(f"Error processing channel {channel_id}: {str(e)}")
                    logger.error(traceback.format_exc())
                    channel_list.append({
                        'name': "Error Channel",
                        'value': f"ID: {channel_id}"
                    })

            if not channel_list:
                await interaction.followup.send("Could not retrieve any channel information.")
                return

            try:
                CHANNELS_PER_PAGE = 5
                total_pages = math.ceil(len(channel_list) / CHANNELS_PER_PAGE)
                
                current_page = 1
                start_idx = (current_page - 1) * CHANNELS_PER_PAGE
                end_idx = start_idx + CHANNELS_PER_PAGE
                current_channels = channel_list[start_idx:end_idx]
                
                embed = self.create_embed(current_channels, total_stats, current_page, total_pages)
                
                view = self.PaginationView(self, channel_list, total_stats)
                
                await interaction.followup.send(embed=embed, view=view)
                    
            except Exception as e:
                logger.error(f"Error sending channel list: {str(e)}")
                logger.error(traceback.format_exc())
                await interaction.followup.send("An error occurred while processing the channel list. Please try again later.")
                
        except Exception as e:
            logger.error(f"Error in list_broadcast_channels: {str(e)}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("An error occurred while executing the command. Please try again later.")

    @app_commands.command(name="broadcast", description="Send a broadcast message to all ball spawn channels")
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(broadcast_type=[
        app_commands.Choice(name="Text and Image", value="both"),
        app_commands.Choice(name="Text Only", value="text"),
        app_commands.Choice(name="Image Only", value="image")
    ])
    async def broadcast(
        self, 
        interaction: discord.Interaction, 
        broadcast_type: str,
        message: Optional[str] = None,
        attachment: Optional[discord.Attachment] = None
    ):
        """Send broadcast messages to all ball spawn channels"""
        if not is_staff(interaction):
            await interaction.response.send_message("You need bot admin permissions to use this command.")
            return

        if broadcast_type == "text" and not message:
            await interaction.response.send_message("You must provide a message when selecting 'Text Only' mode.")
            return
        if broadcast_type == "image" and not attachment:
            await interaction.response.send_message("You must provide an image when selecting 'Image Only' mode.")
            return
        if broadcast_type == "both" and not message and not attachment:
            await interaction.response.send_message("You must provide a message or image when selecting 'Text and Image' mode.")
            return

        try:
            channels = await self.get_broadcast_channels()
            if not channels:
                await interaction.response.send_message("No ball spawn channels are currently configured.")
                return

            await interaction.response.send_message("Broadcasting message...")
            
            success_count = 0
            fail_count = 0
            failed_channels = []
            
            broadcast_message = None
            if message:
                broadcast_message = (
                    "🔔 **System Announcement** 🔔\n"
                    "------------------------\n"
                    f"{message}\n"
                    "------------------------\n"
                    f"*Sent by {interaction.user.name}*"
                )
            
            file = None
            file_data = None
            if attachment and broadcast_type in ["both", "image"]:
                try:
                    file_data = await attachment.read()
                    file = await attachment.to_file()
                except Exception as e:
                    logger.error(f"Error downloading attachment: {str(e)}")
                    logger.error(traceback.format_exc())
                    await interaction.followup.send("An error occurred while downloading the attachment. Only the text message will be sent.")
            
            for channel_id in channels:
                try:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        if broadcast_type == "text":
                            await channel.send(broadcast_message)
                        elif broadcast_type == "image" and file_data:
                            new_file = discord.File(
                                io.BytesIO(file_data),
                                filename=attachment.filename,
                                spoiler=attachment.is_spoiler()
                            )
                            await channel.send(file=new_file)
                        else:  # both
                            if file_data and broadcast_message:
                                new_file = discord.File(
                                    io.BytesIO(file_data),
                                    filename=attachment.filename,
                                    spoiler=attachment.is_spoiler()
                                )
                                await channel.send(broadcast_message, file=new_file)
                            elif file_data:
                                new_file = discord.File(
                                    io.BytesIO(file_data),
                                    filename=attachment.filename,
                                    spoiler=attachment.is_spoiler()
                                )
                                await channel.send(file=new_file)
                            elif broadcast_message:
                                await channel.send(broadcast_message)
                        success_count += 1
                    else:
                        fail_count += 1
                        failed_channels.append(f"Unknown Channel (ID: {channel_id})")
                except Exception as e:
                    logger.error(f"Error broadcasting to channel {channel_id}: {str(e)}")
                    logger.error(traceback.format_exc())
                    fail_count += 1
                    if channel:
                        failed_channels.append(f"{channel.guild.name} - #{channel.name}")
                    else:
                        failed_channels.append(f"Unknown Channel (ID: {channel_id})")
            
            result_message = f"Broadcast complete!\nSuccessfully sent: {success_count} channels\nFailed: {fail_count} channels"
            if failed_channels:
                result_message += "\n\nFailed channels:\n" + "\n".join(failed_channels)
            
            await interaction.followup.send(result_message)
                
        except Exception as e:
            logger.error(f"Error in broadcast: {str(e)}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("An error occurred while executing the command. Please try again later.")

    @app_commands.command(name="broadcast_dm", description="Send a DM broadcast to specific users")
    @app_commands.default_permissions(administrator=True)
    async def broadcast_dm(
        self, 
        interaction: discord.Interaction, 
        message: str,
        user_ids: str
    ):
        """Private Message Broadcasting to Specified users
        
        Args:
            message: the message you are going to send
            user_ids: a comma-separated list of user IDs to send the message to
        """
        if not is_staff(interaction):
            await interaction.response.send_message("You need bot admin permissions to use this command.")
            return

        try:
            user_id_list = [uid.strip() for uid in user_ids.split(",")]
            if not user_id_list:
                await interaction.response.send_message("Please provide at least one user ID.")
                return

            await interaction.response.send_message("Starting DM broadcast...")
            
            success_count = 0
            fail_count = 0
            failed_users = []
            
            dm_message = (
                "🔔 **System DM** 🔔\n"
                "------------------------\n"
                f"{message}\n"
                "------------------------\n"
                f"*Sent by {interaction.user.name}*"
            )
            
            for user_id in user_id_list:
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    if user:
                        await user.send(dm_message)
                        success_count += 1
                    else:
                        fail_count += 1
                        failed_users.append(f"Unknown User (ID: {user_id})")
                except Exception as e:
                    logger.error(f"Error sending DM to user {user_id}: {str(e)}")
                    logger.error(traceback.format_exc())
                    fail_count += 1
                    failed_users.append(f"User ID: {user_id}")
            
            result_message = f"DM broadcast complete!\nSuccessfully sent: {success_count} users\nFailed: {fail_count} users"
            if failed_users:
                result_message += "\n\nFailed users:\n" + "\n".join(failed_users)
            
            await interaction.followup.send(result_message)
                
        except Exception as e:
            logger.error(f"Error in broadcast_dm: {str(e)}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("An error occurred while executing the command. Please try again later.") 
