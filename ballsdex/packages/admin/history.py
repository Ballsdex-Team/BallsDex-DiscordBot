from datetime import timedelta
from typing import TYPE_CHECKING, Literal, cast

import discord
from discord import app_commands
from discord.ui import ActionRow, Button, Select, TextDisplay
from django.db.models import Q
from django.utils import timezone

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.discord import LayoutView
from ballsdex.core.utils.menus import Menu, ModelSource
from ballsdex.core.utils.transformers import BallEnabledTransform, SpecialEnabledTransform
from ballsdex.settings import settings
from bd_models.models import BallInstance, Trade

if TYPE_CHECKING:
    import discord.types.interactions
    from django.db.models import QuerySet

    from ballsdex.packages.trade.cog import Trade as TradeCog


class History(app_commands.Group):
    """
    Trade history management
    """

    async def _build_history_view(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        queryset: "QuerySet[Trade]",
        title: str,
        admin_url_path: str | None = None,
    ):
        cog = cast("TradeCog | None", interaction.client.get_cog("Trade"))
        if not cog:
            await interaction.response.send_message("Trade cog unavailable.", ephemeral=True)
            return

        if not await queryset.aexists():
            await interaction.followup.send("No history found.", ephemeral=True)
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

        menu = Menu(
            interaction.client, view, ModelSource(queryset), cog.trade_list_fmt_cls(select, cog, interaction.user)
        )
        await menu.init()
        await interaction.followup.send(view=view, ephemeral=True)

    def _build_base_queryset(self, sorting: Literal["Recent", "Oldest"], days: int | None) -> "QuerySet[Trade]":
        sort_value = "-date" if sorting == "Recent" else "date"
        queryset = Trade.objects.order_by(sort_value).prefetch_related("player1", "player2")

        if days is not None and days > 0:
            start_date = timezone.now() - timedelta(days=days)
            queryset = queryset.filter(date__ge=start_date)

        return queryset

    @app_commands.command(name="user")
    async def history_user(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
        user2: discord.User | None = None,
        sorting: Literal["Recent", "Oldest"] = "Recent",
        days: int | None = None,
        countryball: BallEnabledTransform | None = None,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Show your trade history.

        Parameters
        ----------
        sorting: Literal["Recent", "Oldest"]
            The sorting order of your trades.
        trade_user: discord.User | None
            The user you want to filter your trade history with.
        days: int | None
            Retrieve trade history from the last x days at most.
        countryball: Ball | None
            The countryball you want to filter the trade history by.
        special: Special | None
            The special you want to filter the trade history by.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)

        title = f"Trade history of {user.display_name}"
        query_params = f"?q={user.id}"
        queryset = self._build_base_queryset(sorting, days)
        if user2:
            title += f" and {user2.display_name}"
            query_params += f"+{user2.id}"
            queryset = queryset.filter(
                (Q(player1__discord_id=user.id, player2__discord_id=user2.id))
                | (Q(player1__discord_id=user2.id, player2__discord_id=user.id))
            )
        else:
            queryset = queryset.filter(Q(player1__discord_id=user.id) | Q(player2__discord_id=user.id))

        if countryball:
            queryset = queryset.filter(Q(tradeobjects__ballinstance__ball=countryball)).distinct()
        if special:
            queryset = queryset.filter(Q(tradeobjects__ballinstance__special=special)).distinct()

        await self._build_history_view(interaction, queryset, title, f"/bd_models/trade/{query_params}")

    @app_commands.command(name="countryball")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def history_ball(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball_id: str,
        sorting: Literal["Recent", "Oldest"] = "Recent",
        days: int | None = None,
    ):
        """
        Show the trade history of a countryball.

        Parameters
        ----------
        countryball_id: str
            The ID of the countryball you want to check the history of.
        sorting: Literal["Recent", "Oldest"]
            The sorting order of your trades.
        days: int | None
            Retrieve trade history from the last x days at most.
        """

        try:
            ball = await BallInstance.objects.aget(id=int(countryball_id, 16))
        except ValueError:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True
            )
            return
        except BallInstance.DoesNotExist:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        queryset = self._build_base_queryset(sorting, days)
        queryset = queryset.filter(tradeobject__ballinstance_id=ball.pk)

        await self._build_history_view(
            interaction,
            queryset,
            f"Trade history for {ball.description(short=True)}",
            f"/bd_models/ballinstance/{ball.pk}/change/",
        )

    @app_commands.command(name="trade")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def trade_info(self, interaction: discord.Interaction["BallsDexBot"], trade_id: str):
        """
        Show the contents of a certain trade.

        Parameters
        ----------
        trade_id: str
            The ID of the trade you want to check the history of.
        """
        cog = cast("TradeCog | None", interaction.client.get_cog("Trade"))
        if not cog:
            await interaction.response.send_message("Trade cog unavailable.", ephemeral=True)
            return

        from ballsdex.packages.trade.history import HistoryView

        try:
            pk = int(trade_id, 16)
        except ValueError:
            await interaction.response.send_message("The trade ID you gave is not valid.", ephemeral=True)
            return
        trade = await Trade.objects.prefetch_related("player1", "player2").aget(id=pk)
        if not trade:
            await interaction.response.send_message("The trade ID you gave does not exist.", ephemeral=True)
            return

        view = HistoryView(interaction.client, trade, admin_view=True)
        await view.initialize(
            trade.player1,
            await cog.fetch_user(trade.player1.discord_id),
            trade.player2,
            await cog.fetch_user(trade.player2.discord_id),
        )
        await interaction.response.send_message(view=view, ephemeral=True)
