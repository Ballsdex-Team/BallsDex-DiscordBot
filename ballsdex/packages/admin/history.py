from datetime import timedelta
from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands
from discord.ui import ActionRow, Button, Select, TextDisplay
from django.db.models import Q
from django.utils import timezone

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.discord import LayoutView
from ballsdex.core.utils import checks
from ballsdex.core.utils.menus import Menu, ModelSource
from ballsdex.settings import settings
from bd_models.models import BallInstance, Trade

if TYPE_CHECKING:
    import discord.types.interactions
    from django.db.models import QuerySet

    from ballsdex.packages.trade.cog import Trade as TradeCog

from .flags import TradeHistoryFlags, UserTradeHistoryFlags


@commands.hybrid_group()
@checks.has_permissions("bd_models.view_trade", "bd_models.view_tradeobject")
async def history(ctx: commands.Context):
    """
    Trade history management
    """
    await ctx.send_help(ctx.command)


async def _build_history_view(
    ctx: commands.Context["BallsDexBot"], queryset: "QuerySet[Trade]", title: str, admin_url_path: str | None = None
):
    cog = cast("TradeCog | None", ctx.bot.get_cog("Trade"))
    if not cog:
        await ctx.send("Trade cog unavailable.", ephemeral=True)
        return

    if not await queryset.aexists():
        await ctx.send("No history found.", ephemeral=True)
        return

    async def callback(interaction: discord.Interaction["BallsDexBot"]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        data = cast("discord.types.interactions.SelectMessageComponentInteractionData", interaction.data)
        trade = await Trade.objects.prefetch_related("player1", "player2").aget(pk=data["values"][0])
        view = cog.history_view_cls(interaction.client, trade, admin_view=True)
        await view.initialize(
            trade.player1,
            await cog.fetch_user(trade.player1.discord_id),
            trade.player2,
            await cog.fetch_user(trade.player2.discord_id),
        )
        await interaction.followup.send(view=view, ephemeral=True)

    view = LayoutView()
    view.add_item(TextDisplay(f"## {title}"))

    if settings.admin_url and admin_url_path:
        view.add_item(ActionRow(Button(label="View online", url=f"{settings.admin_url}{admin_url_path}")))

    action = ActionRow()
    select = Select(placeholder="Choose a trade to display")
    select.callback = callback
    action.add_item(select)
    view.add_item(action)

    menu = Menu(ctx.bot, view, ModelSource(queryset), cog.trade_list_fmt_cls(select, cog, ctx.author))
    await menu.init()
    await ctx.send(view=view, ephemeral=True)


def _build_base_queryset(sort_oldest: bool, days: int | None) -> "QuerySet[Trade]":
    sort_value = "-date" if sort_oldest else "date"
    queryset = Trade.objects.order_by(sort_value).prefetch_related("player1", "player2")

    if days is not None and days > 0:
        start_date = timezone.now() - timedelta(days=days)
        queryset = queryset.filter(date__ge=start_date)

    return queryset


@history.command(name="user")
async def history_user(ctx: commands.Context["BallsDexBot"], user: discord.User, *, flags: UserTradeHistoryFlags):
    """
    Show your trade history.

    Parameters
    ----------
    user: discord.User
        The user you want to check the history of.
    """
    await ctx.defer(ephemeral=True)

    title = f"Trade history of {user.display_name}"
    query_params = f"?q={user.id}"
    queryset = _build_base_queryset(flags.sort_oldest, flags.days)
    if flags.user2:
        title += f" and {flags.user2.display_name}"
        query_params += f"+{flags.user2.id}"
        queryset = queryset.filter(
            (Q(player1__discord_id=user.id, player2__discord_id=flags.user2.id))
            | (Q(player1__discord_id=flags.user2.id, player2__discord_id=user.id))
        )
    else:
        queryset = queryset.filter(Q(player1__discord_id=user.id) | Q(player2__discord_id=user.id))

    if flags.countryball:
        queryset = queryset.filter(Q(tradeobjects__ballinstance__ball=flags.countryball)).distinct()
    if flags.special:
        queryset = queryset.filter(Q(tradeobjects__ballinstance__special=flags.special)).distinct()

    await _build_history_view(ctx, queryset, title, f"/bd_models/trade/{query_params}")


@history.command(name="countryball")
async def history_ball(ctx: commands.Context["BallsDexBot"], countryball_id: str, *, flags: TradeHistoryFlags):
    """
    Show the trade history of a countryball.

    Parameters
    ----------
    countryball_id: str
        The ID of the countryball you want to check the history of.
    """

    try:
        ball = await BallInstance.objects.aget(id=int(countryball_id, 16))
    except ValueError:
        await ctx.send(f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True)
        return
    except BallInstance.DoesNotExist:
        await ctx.send(f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True)
        return

    await ctx.defer(ephemeral=True)

    queryset = _build_base_queryset(flags.sort_oldest, flags.days)
    queryset = queryset.filter(tradeobject__ballinstance_id=ball.pk)

    await _build_history_view(
        ctx, queryset, f"Trade history for {ball.description(short=True)}", f"/bd_models/ballinstance/{ball.pk}/change/"
    )


@history.command(name="trade")
async def trade_info(ctx: commands.Context["BallsDexBot"], trade_id: str):
    """
    Show the contents of a certain trade.

    Parameters
    ----------
    trade_id: str
        The ID of the trade you want to check the history of.
    """
    cog = cast("TradeCog | None", ctx.bot.get_cog("Trade"))
    if not cog:
        await ctx.send("Trade cog unavailable.", ephemeral=True)
        return

    from ballsdex.packages.trade.history import HistoryView

    try:
        pk = int(trade_id, 16)
    except ValueError:
        await ctx.send("The trade ID you gave is not valid.", ephemeral=True)
        return
    trade = await Trade.objects.prefetch_related("player1", "player2").aget(id=pk)
    if not trade:
        await ctx.send("The trade ID you gave does not exist.", ephemeral=True)
        return

    view = HistoryView(ctx.bot, trade, admin_view=True)
    await view.initialize(
        trade.player1,
        await cog.fetch_user(trade.player1.discord_id),
        trade.player2,
        await cog.fetch_user(trade.player2.discord_id),
    )
    await ctx.send(view=view, ephemeral=True)
