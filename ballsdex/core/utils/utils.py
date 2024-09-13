import discord

from ballsdex.settings import settings


def is_staff(interaction: discord.Interaction) -> bool:
    if interaction.guild and interaction.guild.id in settings.admin_guild_ids:
        roles = settings.admin_role_ids + settings.root_role_ids
        if any(role.id in roles for role in interaction.user.roles):  # type: ignore
            return True
    return False
