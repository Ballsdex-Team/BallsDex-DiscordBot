from typing import TYPE_CHECKING

import discord
from discord.ui import ActionRow, Button, Select, Separator, TextDisplay

from ballsdex.core.discord import Container
from ballsdex.core.utils.menus import CountryballFormatter, Menu, ModelSource, TextFormatter, TextSource
from bd_models.models import BallInstance
from settings.models import settings

from .errors import TradeError

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot

    from .cog import Trade

type Interaction = discord.Interaction["BallsDexBot"]


class BulkSelector(Container):
    async def configure(self, bot: "BallsDexBot", cog: "Trade", queryset: QuerySet[BallInstance]):
        assert self.view
        self.bot = bot
        self.cog = cog
        self.queryset = queryset

        # the selected values are going to be stored in the formatter's "defaulted" set
        # such that the selected state is preserved on pagination
        # no need to have a second duplicated set for this
        self.formatter = CountryballFormatter(self.select, max_values=25)
        # we also need to keep the source to know which items are currently being displayed
        self.source = ModelSource(queryset)

        self.menu = Menu(bot, self.view, self.source, self.formatter)
        await self.menu.init(position=7, container=self)

    async def update_display(self):
        assert self.view
        self.balls_count.content = f"-# {len(self.formatter.defaulted)} {settings.plural_collectible_name} selected"
        if not self.formatter.defaulted:
            self.balls.content = "Nothing selected yet"
            return
        text = ""
        # reuse the ordering given in the original queryset
        self.queryset
        async for ball in (
            BallInstance.objects.filter(id__in=self.formatter.defaulted)
            .annotate(**self.queryset.query.annotations)
            .order_by(*self.queryset.query.order_by)
        ):
            text += f"- {ball.description(include_emoji=True, bot=self.bot)}\n"
        menu = Menu(self.bot, self.view, TextSource(text, page_length=3800), TextFormatter(self.balls))
        await menu.init(position=3, container=self)

    header = TextDisplay(f"## Trade bulk selection\nYour selected {settings.plural_collectible_name} are shown below.")
    sep1 = Separator()
    balls = TextDisplay("Nothing selected yet")
    balls_count = TextDisplay(f"-# 0 {settings.plural_collectible_name} selected")
    sep2 = Separator(spacing=discord.SeparatorSpacing.large)
    description = TextDisplay("-# Use the drop-down menu below to select your items.")

    selector_row = ActionRow()

    @selector_row.select(placeholder=f"Select {settings.plural_collectible_name} to add")
    async def select(self, interaction: Interaction, select: Select):
        await interaction.response.defer()
        self.formatter.defaulted.update((int(x) for x in select.values))
        for option in select.options:
            if option.value in select.values:
                self.formatter.defaulted.add(int(option.value))
                option.default = True
            else:
                self.formatter.defaulted.discard(int(option.value))
                option.default = False
        await self.update_display()
        await interaction.edit_original_response(view=self.view)

    sep3 = Separator()
    control_row = ActionRow()

    @control_row.button(label="Select page")
    async def select_all(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        for option in self.select.options:
            self.formatter.defaulted.add(int(option.value))
            option.default = True
        await self.update_display()
        await interaction.edit_original_response(view=self.view)

    @control_row.button(label="Clear")
    async def clear(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        self.formatter.defaulted.clear()
        for option in self.select.options:
            option.default = False
        await self.update_display()
        await interaction.edit_original_response(view=self.view)

    @control_row.button(label="Add to trade", style=discord.ButtonStyle.success)
    async def validate(self, interaction: Interaction, button: Button):
        if not self.formatter.defaulted:
            await interaction.response.send_message("Nothing was selected!", ephemeral=True)
            return

        result = await self.cog.get_trade(interaction.user)
        if result is None:
            await interaction.response.send_message(
                "Your trade was not found, it may have ended before you finished your bulk trade.", ephemeral=True
            )
            return
        trade, trader = result

        try:
            await trader.add_to_proposal(BallInstance.objects.filter(id__in=self.formatter.defaulted))
        except TradeError as e:
            await interaction.response.send_message(e.error_message, ephemeral=True)
        else:
            assert self.view
            await interaction.response.defer()
            self.view.stop()
            for children in self.view.walk_children():
                if hasattr(children, "disabled"):
                    children.disabled = True  # type: ignore
            await interaction.edit_original_response(view=self.view)
            await trade.edit_message(None)
            await interaction.followup.send(
                f"{len(self.formatter.defaulted)} {settings.plural_collectible_name} added.", ephemeral=True
            )
