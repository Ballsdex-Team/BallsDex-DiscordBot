from datetime import timedelta
from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands
from discord.ui import ActionRow, Button, Select, TextDisplay
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.discord import LayoutView
from ballsdex.core.translation import t
from ballsdex.core.utils import checks
from ballsdex.core.utils.menus import Menu, ModelSource
from bd_models.models import BallInstance, Trade
from settings.models import settings

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
        await ctx.send(t("Trade cog unavailable."), ephemeral=True)
        return

    total = await queryset.acount()
    if total == 0:
        await ctx.send(t("No history found."), ephemeral=True)
        return

    async def build_detail_view(pks: list[int], index: int) -> LayoutView:
        trade = await Trade.objects.prefetch_related("player1", "player2").aget(pk=pks[index])
        view = cog.history_view_cls(ctx.bot, trade, admin_view=True)
        await view.initialize(
            trade.player1,
            await cog.fetch_user(trade.player1.discord_id),
            trade.player2,
            await cog.fetch_user(trade.player2.discord_id),
        )

        prev_button = Button(label=t("◀ Previous"), style=discord.ButtonStyle.grey, disabled=index <= 0)
        next_button = Button(label=t("Next ▶"), style=discord.ButtonStyle.grey, disabled=index >= len(pks) - 1)

        async def go_to_prev(interaction: discord.Interaction["BallsDexBot"]):
            await interaction.response.defer()
            await interaction.edit_original_response(view=await build_detail_view(pks, index - 1))

        async def go_to_next(interaction: discord.Interaction["BallsDexBot"]):
            await interaction.response.defer()
            await interaction.edit_original_response(view=await build_detail_view(pks, index + 1))

        prev_button.callback = go_to_prev
        next_button.callback = go_to_next
        view.add_item(ActionRow(prev_button, next_button))
        return view

    async def callback(interaction: discord.Interaction["BallsDexBot"]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        data = cast("discord.types.interactions.SelectMessageComponentInteractionData", interaction.data)
        pk = int(data["values"][0])
        pks = [p async for p in queryset.values_list("pk", flat=True)]
        try:
            index = pks.index(pk)
        except ValueError:
            index = 0
        await interaction.followup.send(view=await build_detail_view(pks, index), ephemeral=True)

    view = LayoutView()
    # NOTE: English-specific plural suffix, not run through ngettext - see t()'s docstring
    view.add_item(
        TextDisplay(
            t("## {title} ({total} trade{plural})").format(title=title, total=total, plural="s" if total != 1 else "")
        )
    )

    if admin_url_path:
        view.add_item(ActionRow(Button(label=t("View online"), url=f"{settings.site_base_url}{admin_url_path}")))

    action = ActionRow()
    select = Select(placeholder=t("Choose a trade to display"))
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
@checks.has_permissions("bd_models.view_trade", "bd_models.view_tradeobject")
async def history_user(ctx: commands.Context["BallsDexBot"], user: discord.User, *, flags: UserTradeHistoryFlags):
    """
    Show your trade history.

    Parameters
    ----------
    user: discord.User
        The user you want to check the history of.
    """
    await ctx.defer(ephemeral=True)

    title = t("Trade history of {user}").format(user=user.display_name)
    query_params = f"?q={user.id}"
    queryset = _build_base_queryset(flags.sort_oldest, flags.days)
    if flags.user2:
        title += t(" and {user}").format(user=flags.user2.display_name)
        query_params += f"+{flags.user2.id}"
        queryset = queryset.filter(
            (Q(player1__discord_id=user.id, player2__discord_id=flags.user2.id))
            | (Q(player1__discord_id=flags.user2.id, player2__discord_id=user.id))
        )
    else:
        queryset = queryset.filter(Q(player1__discord_id=user.id) | Q(player2__discord_id=user.id))

    if flags.countryball:
        queryset = queryset.filter(Q(tradeobject__ballinstance__ball=flags.countryball)).distinct()
    if flags.special:
        queryset = queryset.filter(Q(tradeobject__ballinstance__special=flags.special)).distinct()
    if getattr(flags, "currency", False):
        queryset = queryset.filter(Q(player1_money__gt=0) | Q(player2_money__gt=0))

    await _build_history_view(ctx, queryset, title, f"/bd_models/trade/{query_params}")


@history.command(name="countryball")
@checks.has_permissions("bd_models.view_trade", "bd_models.view_tradeobject")
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
        await ctx.send(
            t("The {collectible} ID you gave is not valid.").format(collectible=settings.collectible_name),
            ephemeral=True,
        )
        return
    except BallInstance.DoesNotExist:
        await ctx.send(
            t("The {collectible} ID you gave does not exist.").format(collectible=settings.collectible_name),
            ephemeral=True,
        )
        return

    await ctx.defer(ephemeral=True)

    queryset = _build_base_queryset(flags.sort_oldest, flags.days)
    queryset = queryset.filter(tradeobject__ballinstance_id=ball.pk)
    if getattr(flags, "currency", False):
        queryset = queryset.filter(Q(player1_money__gt=0) | Q(player2_money__gt=0))

    await _build_history_view(
        ctx,
        queryset,
        t("Trade history for {countryball}").format(countryball=ball.description(short=True)),
        reverse("admin:bd_models_ballinstance_change", args=(ball.pk,)),
    )


@history.command(name="trade")
@checks.has_permissions("bd_models.view_trade", "bd_models.view_tradeobject")
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
        await ctx.send(t("Trade cog unavailable."), ephemeral=True)
        return

    from ballsdex.packages.trade.history import HistoryView

    try:
        pk = int(trade_id, 16)
    except ValueError:
        await ctx.send(t("The trade ID you gave is not valid."), ephemeral=True)
        return
    trade = await Trade.objects.prefetch_related("player1", "player2").aget(id=pk)
    if not trade:
        await ctx.send(t("The trade ID you gave does not exist."), ephemeral=True)
        return

    view = HistoryView(ctx.bot, trade, admin_view=True)
    await view.initialize(
        trade.player1,
        await cog.fetch_user(trade.player1.discord_id),
        trade.player2,
        await cog.fetch_user(trade.player2.discord_id),
    )
    await ctx.send(view=view, ephemeral=True)
