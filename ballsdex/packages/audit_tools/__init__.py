"""
Ballsdex Audit Tools Package
============================

Server inspection and auditing functionality for Ballsdex bot.
"""

from .cog import AuditCog

async def setup(bot):
    """Setup function for loading the audit extension"""
    await bot.add_cog(AuditCog(bot))