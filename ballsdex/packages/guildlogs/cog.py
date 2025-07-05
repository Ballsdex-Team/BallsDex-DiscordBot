import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord.ui import View, Button

from ballsdex.core.bot import BallsDexBot
from ballsdex.settings import settings

log = logging.getLogger("ballsdex.packages.guildlogs")

from discord.ui import View, button, Button
from discord import Interaction, ButtonStyle

class InviteButtonView(View):
    def __init__(self, bot: "BallsDexBot", guild: discord.Guild):
        super().__init__(timeout=1800)
        self.bot = bot
        self.guild = guild
        self.button_disabled = False
        self.message = None

    @button(label="Generate Invite", style=discord.ButtonStyle.primary, custom_id="generate_invite_button", disabled=False)
    async def generate_invite(self, interaction: Interaction, button: Button):

        # Find a channel where the bot can create an invite
        for channel in self.guild.text_channels:
            if channel.permissions_for(self.guild.me).create_instant_invite:
                try:
                    invite = await channel.create_invite(max_age=1800, max_uses=1, unique=True)
                    await interaction.response.send_message(invite.url, ephemeral=True)                    
                    return
                except Exception:
                    continue

        await interaction.response.send_message(
            "Failed to generate invite, permission denied.", ephemeral=True
        )
        log.warning("Failed to generate invite, permission denied.")

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                log.warning("Could not disable invite button after timeout.", exc_info=True)

class GuildLogs(commands.Cog):
  def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

  @commands.Cog.listener()
  async def on_guild_join(self, guild):
    join_time = datetime.now(timezone.utc)
    timestamp = f"<t:{int(join_time.timestamp())}:R>"
    channel = self.bot.get_channel(settings.log_channel)
    embed = discord.Embed(
      description=f"BrawlDex joined {guild.name} {timestamp}.\n\n**Server Details**\nID: {guild.id}\nMember Count: {guild.member_count}\nOwner: <@{guild.owner_id}> (ID: {guild.owner_id})\n\n***Use the button below to generate an invite to the server, the button will expire in a hour!***",
      color=discord.Colour.green(),
      timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Current Server Count: {len(self.bot.guilds)}")
    embed.set_thumbnail(url=self.bot.user.display_avatar.url)
    view = InviteButtonView(bot=self.bot, guild=guild)
    try:
        await channel.send(embed=embed, view=view)
    except Exception:
        log.error("An error occurred while sending the guild join log.", exc_info=True)
                  
  @commands.Cog.listener()
  async def on_guild_remove(self, guild):
    leave_time = datetime.now(timezone.utc)
    timestamp = f"<t:{int(leave_time.timestamp())}:R>"
    channel = self.bot.get_channel(settings.log_channel)
    embed = discord.Embed(
      description=f"BrawlDex left {guild.name} {timestamp}.\n\n**Server Details**\nID: {guild.id}\nMember Count: {guild.member_count}\nOwner: <@{guild.owner_id}> (ID: {guild.owner_id})",
      color=discord.Colour.red(),
      timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Current Server Count: {len(self.bot.guilds)}")
    embed.set_thumbnail(url=self.bot.user.display_avatar.url)
    try:
        await channel.send(embed=embed)
    except Exception:
        log.error("An error occurred while sending the guild leave log.", exc_info=True)
