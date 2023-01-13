from __future__ import annotations

import discord

from typing import TYPE_CHECKING, List, cast

from ballsdex.core.models import BallInstance, Player
from ballsdex.core.utils.paginator import Pages
from ballsdex.core.utils import menus

from ballsdex.packages.players.exchange_interaction import ExchangePlayer, ExchangeConfirmationView

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class CountryballsSource(menus.ListPageSource):
    def __init__(self, entries: List[BallInstance]):
        super().__init__(entries, per_page=25)

    async def format_page(self, menu: CountryballsSelector, balls: List[BallInstance]):
        menu.set_options(balls)
        return True  # signal to edit the page


class CountryballsSelector(Pages):
    def __init__(self, interaction: discord.Interaction, balls: List[BallInstance]):
        self.bot = cast("BallsDexBot", interaction.client)
        source = CountryballsSource(balls)
        super().__init__(source, interaction=interaction)
        self.add_item(self.select_ball_menu)

    def set_options(self, balls: List[BallInstance]):
        options: List[discord.SelectOption] = []
        for ball in balls:
            emoji = self.bot.get_emoji(int(ball.ball.emoji_id))
            favorite = "❤️ " if ball.favorite else ""
            shiny = "✨ " if ball.shiny else ""
            options.append(
                discord.SelectOption(
                    label=f"{favorite}{shiny}{ball.count}# {ball.ball.country}",
                    description=f"ATK: {ball.attack_bonus:+d}% • HP: {ball.health_bonus:+d}% • "
                    f"Caught on {ball.catch_date.strftime('%d/%m/%y %H:%M')}",
                    emoji=emoji,
                    value=f"{ball.pk}",
                )
            )
        self.select_ball_menu.options = options

    @discord.ui.select()
    async def select_ball_menu(self, interaction: discord.Interaction, item: discord.ui.Select):
        await interaction.response.defer(thinking=True)
        ball_instance = await BallInstance.get(
            id=int(interaction.data.get("values")[0])
        ).prefetch_related("ball")
        await self.ball_selected(interaction, ball_instance)

    async def ball_selected(self, interaction: discord.Interaction, ball_instance: BallInstance):
        raise NotImplementedError()


class CountryballsViewer(CountryballsSelector):
    async def ball_selected(self, interaction: discord.Interaction, ball_instance: BallInstance):
        content, file = await ball_instance.prepare_for_message(interaction)
        await interaction.followup.send(content=content, file=file)
        file.close()


class CountryballsExchangerPaginator(CountryballsSelector):
    def __init__(
        self,
        interaction: discord.Interaction,
        player1: ExchangePlayer,
        player2: ExchangePlayer,
        balls_list: List[BallInstance],
    ):
        super().__init__(interaction, balls_list)
        self.timeout = 300

        self.player1 = player1  # the one invoking the exchange
        self.player2 = player2  # the target of the exchange that needs to pick a ball

        # select_ball is already added by underlying __init__
        self.add_item(self.accept_empty)
        self.add_item(self.decline_exchange)
        # our decline button replaces the default stop button
        self.remove_item(self.stop_pages)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        interacting_user = (
            self.player1.user if self.player1.ball is discord.utils.MISSING else self.player2.user
        )
        # instead of checking for the original invoker of this interaction,
        # only the target of this exchange is allowed to interact
        if interaction.user and interaction.user.id in (
            self.bot.owner_id,
            interacting_user.id,
        ):
            return True
        await interaction.response.send_message(
            "This pagination menu cannot be controlled by you, sorry!", ephemeral=True
        )
        return False

    @discord.ui.button(label="Propose nothing")
    async def accept_empty(self, interaction: discord.Interaction, item: discord.ui.Button):
        if not self.player1.ball:
            await interaction.response.send_message(
                "You cannot do an empty exchange", ephemeral=True
            )
            return

        self.player2.ball = None
        view = ExchangeConfirmationView(self.player1, self.player2)
        await interaction.response.send_message(
            f"{self.player1.user.mention} {self.player2.user.mention}",
            embed=view.generate_embed(self.bot),
            view=view,
        )
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline_exchange(self, interaction: discord.Interaction, item: discord.ui.Button):
        await interaction.response.edit_message(
            content=f":x: {self.player2.user.mention} declined this exchange.",
            view=None,
            embed=None,
        )

    async def ball_selected(self, interaction: discord.Interaction, ball_instance: BallInstance):
        self.stop()
        if self.player1.ball is discord.utils.MISSING:
            self.player1.ball = ball_instance
            await self.half_ready_exchange(interaction, self.player1, self.player2.user)
        else:
            self.player2.ball = ball_instance
            view = ExchangeConfirmationView(self.player1, self.player2)
            await interaction.followup.send(
                f"{self.player1.user.mention} {self.player2.user.mention}",
                embed=view.generate_embed(self.bot),
                view=view,
            )

    @classmethod
    async def begin_blank_exchange(
        cls,
        interaction: discord.Interaction,
        user1: discord.abc.User,
        user2: discord.abc.User,
    ):
        """
        None of the two players have decided of their choice yet.
        """
        player1, p1_created = await Player.get_or_create(discord_id=user1.id)
        if not p1_created:
            await player1.fetch_related("balls")
        player2, p2_created = await Player.get_or_create(discord_id=user2.id)
        if not p2_created:
            await player2.fetch_related("balls")

        if (p1_created or not player1.balls) and (p2_created or not player2.balls):
            await interaction.response.send_message(
                "None of you have countryballs to exchange.", ephemeral=True
            )
            return

        if p1_created or not player1.balls:
            return await cls.half_ready_exchange(
                interaction, ExchangePlayer(user1, player1, None), user2
            )
        balls = await player1.balls.all().prefetch_related("ball")
        if p2_created or not player2.balls:
            paginator = cls(
                interaction,
                ExchangePlayer(user1, player1),
                ExchangePlayer(user2, player2, None),
                balls,
            )
            await paginator.start(
                content=":warning: The player you want to exchange with has no countryballs!\n\n"
                "You may still select a countryball which will be offered or cancel now.\n"
                "You have 5 minutes to respond to this request."
            )
        else:
            paginator = cls(
                interaction,
                ExchangePlayer(user1, player1),
                ExchangePlayer(user2, player2),
                balls,
            )
            await paginator.start(
                content=f"You're proposing an exchange to {user2.mention}, please select your "
                "ball first.\nYou have 5 minutes to respond to this request.",
                ephemeral=True,
            )

    @classmethod
    async def half_ready_exchange(
        cls, interaction: discord.Interaction, player1: ExchangePlayer, user2: discord.abc.User
    ):
        """
        One of the players has decided of its choice.
        """
        player2, created = await Player.get_or_create(discord_id=user2.id)
        if not created:
            await player2.fetch_related("balls")

        # it's not a problem if the exchange target doesn't exist, in this case we skip
        # the pagination and jump straight to confirm
        if created or not player2.balls:
            view = ExchangeConfirmationView(player1, ExchangePlayer(user2, player2, None))
            await interaction.followup.send(
                f"Hey {user2.mention}!\n"
                f"{player1.user.mention} proposed an exchange, but you do not have any "
                "countryball yet.\n"
                f"{player1.user.name}, you may still donate that countryball.",
                embed=view.generate_embed(cast("BallsDexBot", interaction.client)),
                view=view,
            )
        else:
            balls = await player2.balls.all().prefetch_related("ball")
            paginator = cls(interaction, player1, ExchangePlayer(user2, player2, None), balls)
            await paginator.start(
                content=f"Hey {user2.mention}!\n"
                f"{interaction.user.name} would like to exchange a countryball with you!\n"
                "Please select a countryball you wish to propose back. You may also propose "
                "nothing (donation) or deny this exchange request.\n"
                "You have 5 minutes to respond to this request."
            )
