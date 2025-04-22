from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bd_models.models import BlacklistedID

if TYPE_CHECKING:
    import discord
    from bd_models.models import BallInstance, Player, Trade

    from ballsdex.core.bot import BallsDexBot


@dataclass(slots=True)
class TradingUser:
    user: "discord.User | discord.Member"
    player: "Player"
    proposal: list["BallInstance"] = field(default_factory=list)
    locked: bool = False
    cancelled: bool = False
    accepted: bool = False
    blacklisted: bool | None = None

    @classmethod
    async def from_trade_model(
        cls, trade: "Trade", player: "Player", bot: "BallsDexBot", is_admin: bool = False
    ):
        proposal = trade.tradeobject_set.filter(player=player).prefetch_related("ballinstance")
        user = await bot.fetch_user(player.discord_id)
        blacklisted = (
            await BlacklistedID.objects.filter(discord_id=player.discord_id).aexists()
            if is_admin
            else None
        )
        return cls(user, player, [x.ballinstance async for x in proposal], blacklisted=blacklisted)
