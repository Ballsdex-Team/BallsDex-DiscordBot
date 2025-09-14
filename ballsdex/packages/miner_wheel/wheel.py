"""Main Miner Wheel class"""

import discord
from typing import List, Optional
from .views import WheelView
from .utils import get_all_miners


class MinerWheel:
    """Main class for creating and managing miner wheels"""
    
    def __init__(self, miners: Optional[List] = None):
        self.miners = miners or []
    
    @classmethod
    async def create_from_database(cls):
        """Create a wheel with all miners from the database"""
        miners = await get_all_miners()
        return cls(miners)
    
    def create_view(self, timeout: int = 300) -> WheelView:
        """Create a Discord view for the wheel"""
        return WheelView(self.miners, timeout=timeout)
    
    def create_embed(self) -> discord.Embed:
        """Create the initial embed for the wheel"""
        return discord.Embed(
            title="🎡 Miner Wheel!", 
            description=f"{len(self.miners)} miners ready to spin!\n Click '🎲 Roll' to start!", 
            color=0x4ECDC4
        )
    
    async def send_to_channel(self, channel: discord.TextChannel, timeout: int = 300) -> discord.Message:
        """Send the wheel to a Discord channel"""
        view = self.create_view(timeout)
        embed = self.create_embed()
        return await channel.send(embed=embed, view=view)
    
    def add_miner(self, miner):
        """Add a miner to the wheel"""
        if miner not in self.miners:
            self.miners.append(miner)
    
    def remove_miner(self, miner):
        """Remove a miner from the wheel"""
        if miner in self.miners:
            self.miners.remove(miner)
    
    def get_miner_count(self) -> int:
        """Get the number of miners in the wheel"""
        return len(self.miners)
    
    def is_empty(self) -> bool:
        """Check if the wheel has no miners"""
        return len(self.miners) == 0