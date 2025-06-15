import datetime

import discord
from discord.ext import commands
from django.db.models import Q

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.utils import checks
from ballsdex.core.utils.paginator import Pages
from ballsdex.packages.trade.display import TradeViewFormat, fill_trade_embed_fields
from ballsdex.packages.trade.trade_user import TradingUser
from ballsdex.settings import settings
from bd_models.models import BallInstance, Player, Trade

from .flags import TradeHistoryFlags, UserTradeHistoryFlags


@commands.hybrid_group()
@checks.has_permissions("bd_models.view_trade", "bd_models.view_tradeobject")
async def history(ctx: commands.Context):
    """
    Trade history management
    """
    await ctx.send_help(ctx.command)


@history.command(name="user")
async def history_user(ctx: commands.Context["BallsDexBot"], user: discord.User, *, flags: UserTradeHistoryFlags):
    """
    Show the trade history of a user.

    Parameters
    ----------
    user: discord.User
        The user you want to check the history of.
    """
    await ctx.defer(ephemeral=True)
    sort_value = "date" if flags.sort_oldest else "-date"

    if flags.days is not None and flags.days < 0:
        await ctx.send("Invalid number of days. Please provide a non-negative value.", ephemeral=True)
        return

    queryset = Trade.objects.filter()
    try:
        player1 = await Player.objects.aget(discord_id=user.id)
        if flags.user2:
            player2 = await Player.objects.aget(discord_id=flags.user2.id)
            query = f"?q={user.id}+{flags.user2.id}"
            queryset = queryset.filter(
                (Q(player1=player1) & Q(player2=player2)) | (Q(player1=player2) & Q(player2=player1))
            )
        else:
            query = f"?q={user.id}"
            queryset = queryset.filter(Q(player1=player1) | Q(player2=player1))
    except Player.DoesNotExist:
        await ctx.send("One or more players are not registered by the bot.", ephemeral=True)
        return

    if flags.countryball:
        queryset = queryset.filter(Q(tradeobjects__ballinstance__ball=flags.countryball)).distinct()

    if flags.days is not None and flags.days > 0:
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=flags.days)
        queryset = queryset.filter(date__range=(start_date, end_date))

    queryset = queryset.order_by(sort_value).prefetch_related("player1", "player2")
    history = await queryset.aall()

    if not history:
        await ctx.send("No history found.", ephemeral=True)
        return

    if flags.user2:
        await ctx.send(f"History of {user.display_name} and {flags.user2.display_name}:")

    url = f"{settings.admin_url}/bd_models/trade/{query}" if settings.admin_url else None
    source = TradeViewFormat(history, user.display_name, ctx.bot, True, url)
    pages = Pages(ctx, source)
    await pages.start(ephemeral=True)


@history.command(name="countryball")
async def history_ball(ctx: commands.Context["BallsDexBot"], countryball_id: str, *, flags: TradeHistoryFlags):
    """
    Show the trade history of a countryball.

    Parameters
    ----------
    countryball_id: str
        The ID of the countryball you want to check the history of.
    """
    sort_value = "date" if flags.sort_oldest else "-date"

    try:
        pk = int(countryball_id, 16)
    except ValueError:
        await ctx.send(f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True)
        return

    ball = await BallInstance.objects.aget_or_none(id=pk)
    if not ball:
        await ctx.send(f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True)
        return

    await ctx.defer(ephemeral=True)
    if flags.days is not None and flags.days < 0:
        await ctx.send("Invalid number of days. Please provide a non-negative value.", ephemeral=True)
        return

    queryset = Trade.objects
    if flags.days is None or flags.days == 0:
        queryset = queryset.filter(tradeobjects__ballinstance_id=pk)
    else:
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=flags.days)
        queryset = queryset.filter(tradeobjects__ballinstance_id=pk, date__range=(start_date, end_date))
    trades = await queryset.order_by(sort_value).prefetch_related("player1", "player2").aall()

    if not trades:
        await ctx.send("No history found.", ephemeral=True)
        return

    url = f"{settings.admin_url}/bd_models/ballinstance/{ball.pk}/change/" if settings.admin_url else None
    source = TradeViewFormat(trades, f"{settings.collectible_name} {ball}", ctx.bot, True, url)
    pages = Pages(ctx, source)
    await pages.start(ephemeral=True)


@history.command(name="trade")
async def trade_info(ctx: commands.Context["BallsDexBot"], trade_id: str):
    """
    Show the contents of a certain trade.

    Parameters
    ----------
    trade_id: str
        The ID of the trade you want to check the history of.
    """
    try:
        pk = int(trade_id, 16)
    except ValueError:
        await ctx.send("The trade ID you gave is not valid.", ephemeral=True)
        return
    trade = await Trade.objects.prefetch_related("player1", "player2").aget_or_none(id=pk)
    if not trade:
        await ctx.send("The trade ID you gave does not exist.", ephemeral=True)
        return
    embed = discord.Embed(
        title=f"Trade {trade.pk:0X}",
        url=(f"{settings.admin_url}/bd_models/trade/{trade.pk}/change/" if settings.admin_url else None),
        description=f"Trade ID: {trade.pk:0X}",
        timestamp=trade.date,
    )
    embed.set_footer(text="Trade date: ")
    fill_trade_embed_fields(
        embed,
        ctx.bot,
        await TradingUser.from_trade_model(trade, trade.player1, ctx.bot, True),
        await TradingUser.from_trade_model(trade, trade.player2, ctx.bot, True),
        is_admin=True,
    )
    await ctx.send(embed=embed, ephemeral=True)
