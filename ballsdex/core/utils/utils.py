from typing import TYPE_CHECKING, List, Union

import discord

from bd_models.enums import PrivacyPolicy
from bd_models.models import Player

from .checks import get_user_for_check

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def is_staff(interaction: discord.Interaction["BallsDexBot"], *perms: str) -> bool:
    """
    Checks if an interacting user checks one of the following conditions:

    - The user is a bot owner
    - The user has a role considered root or admin

    Parameters
    ----------
    interaction: Interaction[BallsDexBot]
        The interaction of the user to check.
    perms: *str
        Django permissions to verify. If empty, only staff status will be checked.

    Returns
    -------
    bool
        `True` if the user is a staff, `False` otherwise.
    """
    user = await get_user_for_check(interaction.client, interaction.user)
    if isinstance(user, bool):
        return user
    if not user.is_staff:
        return False
    return await user.ahas_perms(perms)


async def inventory_privacy(
    bot: "BallsDexBot",
    interaction: discord.Interaction["BallsDexBot"],
    player: Player,
    user_obj: Union[discord.User, discord.Member],
):
    """
    Check if the inventory of a user is viewable in the given context. If not, a followup response will be sent with a
    proper message.

    Parameters
    ----------
    bot: BallsDexBot
        Bot object
    interaction: Interaction[BallsDexBot]
        Interaction of the command.
    player: Player
        Ballsdex Player object of the user whose inventory is being inspected.
    user_obj: discord.User | discord.Member
        Discord user object of the user whose inventory is being inspected.

    Returns
    -------
    bool
        `True` if the inventory can be viewed, else `False`. If this is `False`, you should exit the command.
    """
    privacy_policy = player.privacy_policy
    interacting_player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
    if interaction.user.id == player.discord_id:
        return True
    if is_staff(interaction):
        return True
    if privacy_policy == PrivacyPolicy.DENY:
        await interaction.followup.send("This user has set their inventory to private.", ephemeral=True)
        return False
    elif privacy_policy == PrivacyPolicy.FRIENDS:
        if not await interacting_player.is_friend(player):
            await interaction.followup.send(
                "This users inventory can only be viewed from users they have added as friends.", ephemeral=True
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
            await interaction.followup.send("This user has set their inventory to private.", ephemeral=True)
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
