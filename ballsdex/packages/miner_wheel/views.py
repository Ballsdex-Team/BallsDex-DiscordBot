"""Discord UI Views for the Miner Wheel"""

import discord
import random
from typing import List
from .utils import get_miner_image_path

STAFF_ROLE_ID = "1405512666901909635"
COLOR_WINNER = 0xFFD700
COLOR_ALL_DONE = 0xFF6B6B
COLOR_RESET = 0x4ECDC4

class WheelView(discord.ui.View):
    """Interactive Discord view for the miner wheel"""
    
    def __init__(self, miners: List, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.miners = miners.copy()
        self.all_miners = miners.copy()
        self.winner = None
        self.winner_ball = None
        self.processing = False
    
    def has_required_role(self, interaction: discord.Interaction) -> bool:
        """Check if user has the required role"""
        if not interaction.guild:
            return False
        
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return False
            
        # Check if user has the staff role
        return any(str(role.id) == STAFF_ROLE_ID for role in member.roles)
    
    async def safe_process(self, interaction: discord.Interaction) -> bool:
        """Handle interaction processing safety with role check"""
        if not self.has_required_role(interaction):
            await interaction.response.send_message("❌ You need the staff role to use this wheel!", ephemeral=True)
            return False
            
        if self.processing:
            await interaction.response.send_message("Please wait...", ephemeral=True)
            return False
        
        self.processing = True
        await interaction.response.defer()
        return True
    
    def create_winner_embed(self, title: str, color: int) -> discord.Embed:
        """Create an embed for displaying the winner"""
        return discord.Embed(
            title=title, 
            description=f"**{self.winner}**!\n {len(self.miners)} miners remaining", 
            color=color
        )
    
    async def send_winner_response(self, interaction: discord.Interaction, embed: discord.Embed):
        """Send the winner response with image if available"""
        try:
            image_path = get_miner_image_path(self.winner_ball)
            file = discord.File(image_path, filename="winner.png")
            embed.set_image(url="attachment://winner.png")
            await interaction.edit_original_response(embed=embed, attachments=[file], view=self)
        except FileNotFoundError:
            await interaction.edit_original_response(embed=embed, view=self)
            print(f"Image not found for winner: {self.winner_ball}")
        except Exception as e:
            await interaction.edit_original_response(content=f"An error occurred: {str(e)}", view=self)
    
    @discord.ui.button(label='🎲 Roll', style=discord.ButtonStyle.primary)
    async def roll(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.safe_process(interaction):
            return
            
        try:
            if not self.miners:
                await interaction.followup.send("No miners left!", ephemeral=True)
                return
                
            self.winner_ball = random.choice(self.miners)
            self.winner = self.winner_ball.country
            
            embed = self.create_winner_embed("🎯 Winner!", COLOR_WINNER)
            await self.send_winner_response(interaction, embed)
            
        finally:
            self.processing = False
    
    @discord.ui.button(label='🗑️ Remove & Roll', style=discord.ButtonStyle.danger)
    async def remove_roll(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.safe_process(interaction):
            return
            
        try:
            if not self.winner_ball:
                await interaction.followup.send("No winner to remove!", ephemeral=True)
                return
                
            if self.winner_ball in self.miners:
                self.miners.remove(self.winner_ball)
                
            if not self.miners:
                embed = discord.Embed(title="🏁 All Done!", description="No miners left!", color=COLOR_ALL_DONE)
                await interaction.edit_original_response(embed=embed, attachments=[], view=None)
                return
            
            self.winner_ball = random.choice(self.miners)
            self.winner = self.winner_ball.country
            
            embed = self.create_winner_embed("🎯 New Winner!", COLOR_WINNER)
            await self.send_winner_response(interaction, embed)
            
        finally:
            self.processing = False
    
    @discord.ui.button(label='🔄 Reset', style=discord.ButtonStyle.secondary)
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.safe_process(interaction):
            return
            
        try:
            self.miners = self.all_miners.copy()
            self.winner = None
            self.winner_ball = None
            
            embed = discord.Embed(
                title="🎡 Wheel Reset!", 
                description=f"{len(self.miners)} miners ready to spin!", 
                color=COLOR_RESET
            )
            await interaction.edit_original_response(embed=embed, attachments=[], view=self)
            
        finally:
            self.processing = False
    
    async def on_timeout(self):
        """Handle view timeout"""
        # Disable all buttons when the view times out
        for item in self.children:
            item.disabled = True
        # Optionally, send a message to indicate the timeout
        await self.message.channel.send("The wheel has timed out. Please start a new game.")

