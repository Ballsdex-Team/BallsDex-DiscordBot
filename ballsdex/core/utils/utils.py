from typing import TYPE_CHECKING, List, Union

import discord

from ballsdex.core.models import Player, PrivacyPolicy
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


def is_staff(interaction: discord.Interaction["BallsDexBot"]) -> bool:
    if interaction.user.id in interaction.client.owner_ids:
        return True
    if settings.admin_channel_ids:
        if interaction.channel_id not in settings.admin_channel_ids:
            return False
    if interaction.guild and interaction.guild.id in settings.admin_guild_ids:
        roles = settings.admin_role_ids + settings.root_role_ids
        if any(role.id in roles for role in interaction.user.roles):  # type: ignore
            return True
    return False


async def inventory_privacy(
    bot: "BallsDexBot",
    interaction: discord.Interaction["BallsDexBot"],
    player: Player,
    user_obj: Union[discord.User, discord.Member],
):
    privacy_policy = player.privacy_policy
    interacting_player, _ = await Player.get_or_create(discord_id=interaction.user.id)
    if interaction.user.id == player.discord_id:
        return True
    if is_staff(interaction):
        return True
    if privacy_policy == PrivacyPolicy.DENY:
        await interaction.followup.send(
            "This user has set their inventory to private.", ephemeral=True
        )
        return False
    elif privacy_policy == PrivacyPolicy.FRIENDS:
        if not await interacting_player.is_friend(player):
            await interaction.followup.send(
                "This users inventory can only be viewed from users they have added as friends.",
                ephemeral=True,
            )
            return False
    elif privacy_policy == PrivacyPolicy.SAME_SERVER:
        if not bot.intents.members:
            await interaction.followup.send(
                "This user has their policy set to `Same Server`, "
                "however I do not have the `members` intent to check this.",
                ephemeral=True,
            )
            return False
        if interaction.guild is None:
            await interaction.followup.send(
                "This user has set their inventory to private.", ephemeral=True
            )
            return False
        elif interaction.guild.get_member(user_obj.id) is None:
            await interaction.followup.send("This user is not in the server.", ephemeral=True)
            return False
    return True


async def can_mention(players: List[Player]) -> discord.AllowedMentions:
    can_mention = []
    for player in players:
        if player.can_be_mentioned:
            can_mention.append(discord.Object(id=player.discord_id))
    return discord.AllowedMentions(users=can_mention, roles=False, everyone=False)
