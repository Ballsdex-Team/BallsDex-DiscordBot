from io import BytesIO

from django.db.models import Q

from bd_models.models import BallInstance, Player, Trade, TradeObject
from settings.models import settings


async def get_items_csv(player: Player) -> BytesIO:
    """
    Get a CSV file with all items of the player.
    """
    balls = BallInstance.objects.filter(player=player).prefetch_related("ball", "trade_player", "special")
    txt = f"id,hex id,{settings.collectible_name},catch date,trade_player,special,attack,attack bonus,hp,hp_bonus\n"
    async for ball in balls:
        txt += (
            f"{ball.id},{ball.id:0X},{ball.ball.country},{ball.catch_date},"  # type: ignore
            f"{ball.trade_player.discord_id if ball.trade_player else 'None'},{ball.special},"
            f"{ball.attack},{ball.attack_bonus},{ball.health},{ball.health_bonus}\n"
        )
    return BytesIO(txt.encode("utf-8"))


async def get_trades_csv(player: Player) -> BytesIO:
    """
    Get a CSV file with all trades of the player.
    """
    trade_history = (
        Trade.objects.filter(Q(player1=player) | Q(player2=player))
        .order_by("date")
        .prefetch_related("player1", "player2")
    )
    txt = "id,date,player1,player2,player1 received,player2 received\n"
    async for trade in trade_history:
        player1_items = TradeObject.objects.filter(trade=trade, player=trade.player1).prefetch_related("ballinstance")
        player2_items = TradeObject.objects.filter(trade=trade, player=trade.player2).prefetch_related("ballinstance")
        txt += (
            f"{trade.pk},{trade.date},{trade.player1.discord_id},{trade.player2.discord_id},"
            f"{','.join([str(i.ballinstance) async for i in player2_items])},"
            f"{','.join([str(i.ballinstance) async for i in player1_items])}\n"
        )
    return BytesIO(txt.encode("utf-8"))
