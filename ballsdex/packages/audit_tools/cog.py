"""
cog.py - Discord commands for audit functionality
=================================================

Discord.py cog with audit commands.
"""

import discord
from discord.ext import commands
from typing import Optional
from datetime import datetime

from .audit import ServerAuditor

# Intents configuration
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True  # If you need message content

ADMIN_GUILD_ID = 1405512069465374730
ADMIN_ROLE_ID = 1405512666901909635

class AuditCog(commands.Cog):
    """Audit commands for server inspection"""
    
    def __init__(self, bot):
        self.bot = bot
        self.auditor = ServerAuditor(bot)
    
    @commands.hybrid_command(
        name="audit",
        description="Audit a server for inspection",
        guild_ids=[1405512069465374730]  # Only this guild/server will see the command
    )
    async def audit_server(self, ctx, guild_id: Optional[str] = None):
        """Audit a server and show detailed information"""

        # Restrict to specific role
        if not any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles):
            await ctx.send("❌ You do not have permission to use this command.", ephemeral=True)
            return

        # Determine which guild to audit
        if guild_id:
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    await ctx.send("❌ Guild not found with that ID")
                    return
            except ValueError:
                await ctx.send("❌ Invalid guild ID format")
                return
        else:
            guild = ctx.guild

        # Send loading message
        embed = discord.Embed(
            title="🔍 Auditing Server...",
            description=f"Analyzing {guild.name}...",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)  # <-- Replace reply with send

        try:
            # Get server information
            start_time = datetime.now()
            server_data = await self.auditor.get_basic_server_info(guild)
            print("Audit data received")  # <--- Add this line
            end_time = datetime.now()
            process_time = (end_time - start_time).total_seconds()

            # Create result embed
            embed = discord.Embed(
                title=f"📋 Server Audit: {server_data['basic']['name']}",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )

            # Basic info
            basic = server_data['basic']
            embed.add_field(
                name="📊 Basic Information",
                value=f"**Owner:** {basic['owner']}\n"
                      f"**Created:** {basic['created']}\n"
                      f"**ID:** {basic['id']}\n"
                      f"**Verification:** {basic['verification_level']}",
                inline=False
            )

            # Member info
            embed.add_field(
                name="👥 Members",
                value=f"**Total:** {basic['member_count']:,}\n"
                      f"**Humans:** {basic['humans']:,}\n"
                      f"**Bots:** {basic['bots']:,}\n"
                      f"**Online:** {basic['online']:,}\n"
                      f"**Administrators:** {len(basic['administrators'])}",
                inline=True
            )

            # Structure info
            channels = server_data['channels']
            roles = server_data['roles']
            embed.add_field(
                name="🏗️ Structure",
                value=f"**Channels:** {channels['total']}\n"
                      f"**Text:** {channels['text']}\n"
                      f"**Voice:** {channels['voice']}\n"
                      f"**Categories:** {channels['categories']}\n"
                      f"**Roles:** {roles['total']}\n"
                      f"**Admin Roles:** {roles['with_admin']}",
                inline=True
            )

            # Show administrators if any
            if basic['administrators']:
                admin_list = []
                for admin in basic['administrators'][:10]:  # Show max 10
                    admin_list.append(f"• {admin['name']} (joined {admin['joined']})")

                if len(basic['administrators']) > 10:
                    admin_list.append(f"• ... and {len(basic['administrators']) - 10} more")

                embed.add_field(
                    name="👑 Administrators",
                    value='\n'.join(admin_list),
                    inline=False
                )

            # Set guild icon
            if guild.icon:
                embed.set_thumbnail(url=str(guild.icon))

            embed.set_footer(text=f"Processed in {process_time:.1f}s")
            print("Embed built, sending...")  # <--- Add this line

            # Prepare member list text
            member_lines = []
            for member in guild.members:
                member_lines.append(f"{str(member)} (ID: {member.id})")
            member_text = "\n".join(member_lines)

            # Create discord.File object
            import io
            member_file = discord.File(io.StringIO(member_text), filename="members.txt")

            # Send embed and file together
            await ctx.send(embed=embed, file=member_file)
            print("Message sent!")  # <--- Add this line
        except Exception as e:
            print("Exception in audit_server:", e)
            error_embed = discord.Embed(
                title="❌ Audit Failed",
                description=f"Error during audit: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=error_embed)
    
    @commands.hybrid_command(
        name="quick_audit",
        description="Quick server overview",
        guild_ids=[ADMIN_GUILD_ID],
        default_member_permissions=discord.Permissions(administrator=True)  # <-- Add this line
    )
    async def quick_audit(self, ctx, guild_id: Optional[str] = None):
        """Quick server audit with essential info only"""

        # Restrict to specific role
        if not any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles):
            await ctx.send("❌ You do not have permission to use this command.", ephemeral=True)
            return

        # Determine guild
        if guild_id:
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    await ctx.send("❌ Guild not found")
                    return
            except ValueError:
                await ctx.send("❌ Invalid guild ID")
                return
        else:
            guild = ctx.guild
        
        # Make sure members are loaded
        if not guild.chunked or len(guild.members) < guild.member_count:
            try:
                members = [m async for m in guild.fetch_members(limit=None)]
            except Exception as e:
                print("Fetch members failed:", e)
                members = guild.members
        else:
            members = guild.members
        
        # Count members
        humans = sum(1 for m in members if not m.bot)
        bots = sum(1 for m in members if m.bot)
        admins = sum(1 for m in members if not m.bot and m.guild_permissions.administrator)
        
        embed = discord.Embed(
            title=f"⚡ Quick Audit: {guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="👥 Members",
            value=f"**Total:** {guild.member_count:,}\n"
                  f"**Humans:** {humans:,}\n"
                  f"**Bots:** {bots:,}\n"
                  f"**Admins:** {admins}",
            inline=True
        )
        
        embed.add_field(
            name="🏗️ Structure", 
            value=f"**Channels:** {len(guild.channels)}\n"
                  f"**Roles:** {len(guild.roles)}\n"
                  f"**Created:** {discord.utils.format_dt(guild.created_at, 'R')}",
            inline=True
        )
        
        embed.add_field(
            name="🔒 Security",
            value=f"**Verification:** {guild.verification_level}\n"
                  f"**2FA:** {'Required' if guild.mfa_level else 'Not Required'}\n"
                  f"**Content Filter:** {guild.explicit_content_filter}",
            inline=True
        )
        
        if guild.icon:
            embed.set_thumbnail(url=str(guild.icon))
        
        await ctx.send(embed=embed)