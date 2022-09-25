import discord

from typing import TYPE_CHECKING, Optional, cast
from tortoise.transactions import in_transaction
from dataclasses import dataclass

from ballsdex.core.models import Player, BallInstance

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


@dataclass
class ExchangePlayer:
    user: discord.abc.User
    player: Player
    ball: Optional[BallInstance] = discord.utils.MISSING
    accepted: Optional[bool] = None


class ExchangeConfirmationView(discord.ui.View):
    def __init__(self, player1: ExchangePlayer, player2: ExchangePlayer):
        super().__init__()
        self.player1 = player1
        self.player2 = player2

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        bot = cast("BallsDexBot", interaction.client)
        if not await bot.blacklist_check(interaction):
            return False
        if interaction.user and interaction.user.id in (
            bot.owner_id,
            self.player1.user.id,
            self.player2.user.id,
        ):
            return True
        await interaction.response.send_message(
            "You are not part of this exchange.", ephemeral=True
        )
        return False

    def generate_embed(self, bot: "BallsDexBot") -> discord.Embed:
        embed = discord.Embed(title="Countryball exchange", description="Validate this exchange")

        def make_field(player: ExchangePlayer):
            if player.accepted is True:
                approval = ":white_check_mark: Accepted!"
            elif player.accepted is False:
                approval = ":x: Denied"
            elif player.accepted is None:
                approval = "*Pending approval*"
            if player.ball:
                emoji = bot.get_emoji(player.ball.ball.emoji_id) or ""
                value = (
                    "You will give this countryball:\n"
                    f"{emoji} `{player.ball.count}#` {player.ball.ball.country}"
                )
            else:
                value = "You are not giving anything back."
            embed.add_field(
                name=player.user.name,
                value=f"{value}\n\n{approval}",
                inline=True,
            )

        make_field(self.player1)
        make_field(self.player2)

        if self.player1.accepted and self.player2.accepted:
            embed.color = discord.Colour.green()
            embed.set_footer(text="The exchange is done!")
        elif self.player1.accepted is False or self.player2.accepted is False:
            embed.color = discord.Colour.red()
            embed.set_footer(text="The exchange was denied.")
        else:
            embed.color = discord.Colour.blurple()
            embed.set_footer(text="Click the buttons below to accept or deny.")

        return embed

    async def proceed_to_exchange(self, interaction: discord.Interaction):
        async with in_transaction():
            if self.player1.ball:
                self.player1.ball.player = self.player2.player
                self.player1.ball.trade_player = self.player1.player
                await self.player1.ball.save()
            if self.player2.ball:
                self.player2.ball.player = self.player1.player
                self.player2.ball.trade_player = self.player2.player
                await self.player2.ball.save()
        self.accept_button.disabled = True
        self.deny_button.disabled = True
        await interaction.response.edit_message(
            embed=self.generate_embed(cast("BallsDexBot", interaction.client)), view=self
        )
        self.stop()

    async def cancel_exchange(self, interaction: discord.Interaction):
        self.accept_button.disabled = True
        self.deny_button.disabled = True
        await interaction.response.edit_message(
            embed=self.generate_embed(cast("BallsDexBot", interaction.client)), view=self
        )
        self.stop()

    @discord.ui.button(
        style=discord.ButtonStyle.success, emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}"
    )
    async def accept_button(self, interaction: discord.Interaction, item: discord.ui.Button):
        if interaction.user.id == self.player1.user.id:
            exchange_player = self.player1
            other = self.player2
        elif interaction.user.id == self.player2.user.id:
            exchange_player = self.player2
            other = self.player1
        else:
            return  # shouldn't be possible

        if exchange_player.accepted:
            await interaction.response.send_message(
                "You already accepted this exchange.", ephemeral=True
            )
            return
        exchange_player.accepted = True
        if other.accepted:
            await self.proceed_to_exchange(interaction)
        else:
            await interaction.response.edit_message(
                embed=self.generate_embed(cast("BallsDexBot", interaction.client))
            )

    @discord.ui.button(
        style=discord.ButtonStyle.danger,
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
    )
    async def deny_button(self, interaction: discord.Interaction, item: discord.ui.Button):
        if interaction.user.id == self.player1.user.id:
            exchange_player = self.player1
        elif interaction.user.id == self.player2.user.id:
            exchange_player = self.player2
        else:
            return  # shouldn't be possible
        exchange_player.accepted = False
        await self.cancel_exchange(interaction)
