from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ballsdex.core.models import BlacklistedID

if TYPE_CHECKING:
    import discord

    from ballsdex.core.bot import BallsDexBot
    from ballsdex.core.models import BallInstance, Player, Trade


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
    async def from_match_model(
        cls, trade: "Trade", player: "Player", bot: "BallsDexBot", is_admin: bool = False
    ):
        """Create a MatchingUser from a trade model (for history viewing)."""
        proposal = await trade.tradeobjects.filter(player=player).prefetch_related("ballinstance")
        user = await bot.fetch_user(player.discord_id)
        blacklisted = (
            await BlacklistedID.exists(discord_id=player.discord_id) if is_admin else None
        )
        return cls(user, player, [x.ballinstance for x in proposal], blacklisted=blacklisted)
