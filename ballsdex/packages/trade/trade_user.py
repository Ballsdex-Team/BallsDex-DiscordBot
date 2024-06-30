from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord

    from ballsdex.core.bot import BallsDexBot
    from ballsdex.core.models import BallInstance, Player, Trade


@dataclass(slots=True)
class TradingUser:
    user: "discord.User | discord.Member"
    player: "Player"
    proposal: list["BallInstance"] = field(default_factory=list)
    locked: bool = False
    cancelled: bool = False
    accepted: bool = False

    @classmethod
    async def from_trade_model(cls, trade: "Trade", player: "Player", bot: "BallsDexBot"):
        proposal = await trade.tradeobjects.filter(player=player).prefetch_related("ballinstance")
        user = await bot.fetch_user(player.discord_id)
        return cls(user, player, [x.ballinstance for x in proposal])
