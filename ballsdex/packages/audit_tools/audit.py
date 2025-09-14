"""
audit.py - Core audit functionality
===================================

Server inspection and analysis functionality.
"""

import discord
from datetime import datetime, timedelta
from typing import Dict, List
import asyncio

class ServerAuditor:
    """Core server auditing functionality"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def get_basic_server_info(self, guild: discord.Guild) -> Dict:
        """Get basic server information"""

        print("Starting audit for guild:", guild.name)  # Debug

        # Make sure we have member data
        if not guild.chunked:
            print("Guild not chunked, chunking now...")  # Debug
            try:
                await guild.chunk(cache=True)
            except Exception as e:
                print("Chunking failed:", e)
        print("Members loaded:", len(guild.members))  # Debug
        
        # Ensure member list is populated
        if not guild.chunked or len(guild.members) < guild.member_count:
            print("Fetching all members...")
            try:
                members = await asyncio.wait_for(
                    [m async for m in guild.fetch_members(limit=None)],
                    timeout=10
                )
                print(f"Fetched {len(members)} members.")
            except Exception as e:
                print("Fetch members failed:", e)
                members = guild.members
        else:
            members = guild.members

        humans = 0
        bots = 0
        online = 0
        admins = []

        print("Starting member processing...")
        for i, member in enumerate(members):
            print(f"Processing member {i}: {member}")
            try:
                if member.bot:
                    bots += 1
                else:
                    humans += 1

                if member.status != discord.Status.offline:
                    online += 1

                if not member.bot and member.guild_permissions.administrator:
                    admins.append({
                        'name': str(member),
                        'id': member.id,
                        'joined': member.joined_at.strftime('%Y-%m-%d') if member.joined_at else 'Unknown'
                    })
            except Exception as e:
                print(f"Error processing member {i}: {e}")
        
        # Basic server info
        basic_info = {
            'name': guild.name,
            'id': guild.id,
            'owner': str(guild.owner) if guild.owner else 'Unknown',
            'owner_id': guild.owner.id if guild.owner else None,
            'created': guild.created_at.strftime('%Y-%m-%d'),
            'member_count': guild.member_count,
            'humans': humans,
            'bots': bots,
            'online': online,
            'verification_level': str(guild.verification_level),
            'administrators': admins
        }
        
        # Channel info
        text_channels = len([c for c in guild.channels if isinstance(c, discord.TextChannel)])
        voice_channels = len([c for c in guild.channels if isinstance(c, discord.VoiceChannel)])
        categories = len([c for c in guild.channels if isinstance(c, discord.CategoryChannel)])
        
        channel_info = {
            'total': len(guild.channels),
            'text': text_channels,
            'voice': voice_channels,
            'categories': categories
        }
        
        # Role info
        role_info = {
            'total': len(guild.roles),
            'with_admin': len([r for r in guild.roles if r.permissions.administrator])
        }
        
        return {
            'basic': basic_info,
            'channels': channel_info,
            'roles': role_info
        }