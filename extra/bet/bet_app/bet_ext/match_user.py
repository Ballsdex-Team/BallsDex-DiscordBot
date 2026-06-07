from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bd_models.models import BlacklistedID

if TYPE_CHECKING:
    import discord

    from ballsdex.core.bot import BallsDexBot
    from bd_models.models import BallInstance, Player, Trade


@dataclass(slots=True)
class MatchingUser:
    user: "discord.User | discord.Member"
    player: "Player"
    bet: list["BallInstance"] = field(default_factory=list)
    locked: bool = False
    cancelled: bool = False
    matched: bool = False  # True if this player won the match
    blacklisted: bool | None = None

    @classmethod
    async def from_match_model(cls, trade: "Trade", player: "Player", bot: "BallsDexBot", is_admin: bool = False):
        """Create a MatchingUser from a trade model (for history viewing)."""
        proposal = [x async for x in trade.tradeobject_set.prefetch_related("ballinstance").filter(player=player)]
        user = await bot.fetch_user(player.discord_id)
        blacklisted = await BlacklistedID.objects.filter(discord_id=player.discord_id).aexists() if is_admin else None
        return cls(user, player, [x.ballinstance for x in proposal], blacklisted=blacklisted)
