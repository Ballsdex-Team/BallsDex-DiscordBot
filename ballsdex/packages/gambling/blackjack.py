import random
from typing import TYPE_CHECKING

import discord
from discord.ui import Button, button, View

from ballsdex.settings import settings
from ballsdex.core.models import BallInstance
from ballsdex.core.utils.transformers import BallInstanceTransform

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Card:
    SUITS = [":heart:", ":diamonds:", ":clubs:", ":spades:"]
    VALUES = [2, 3, 4, 5, 6, 7, 8, 9, 10, "J", "Q", "K", "A"]

    def __init__(self, value: int | str, suit: str) -> None:
        self.value = value
        self.suit = suit

    def __str__(self):
        return f"{self.value}{self.suit}"

    def get_value(self):
        if isinstance(self.value, int):
            return self.value
        elif self.value in ["J", "Q", "K"]:
            return 10
        elif self.value == "A":
            return 11


class BlackjackGame:
    def __init__(self):
        self.deck = [Card(value, suit) for suit in Card.SUITS for value in Card.VALUES]
        random.shuffle(self.deck)

    def deal_hand(self):
        return [self.deck.pop(), self.deck.pop()]

    @staticmethod
    def calculate_hand_value(hand):
        value = sum(card.get_value() for card in hand)
        aces = sum(1 for card in hand if card.value == "A")
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    @staticmethod
    def hand_to_str(hand):
        return " ".join(str(card) for card in hand)


class BlackjackGameView(View):
    def __init__(
        self,
        bot: "BallsDexBot",
        player,
        bj_game: BlackjackGame,
        countryball: BallInstanceTransform,
    ):
        super().__init__()
        self.bot = bot
        self.player = player
        self.bj_game = bj_game
        self.countryball = countryball
        self.player_hand = [bj_game.deck.pop()]
        self.ai_hand = [bj_game.deck.pop()]
        self.player_value = bj_game.calculate_hand_value(self.player_hand)
        self.ai_value = bj_game.calculate_hand_value(self.ai_hand)
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player.discord_id:
            await interaction.response.send_message(
                "You cannot interact with this view!", ephemeral=True
            )
            return False
        return True

    async def send_initial_message(self, interaction: discord.Interaction):
        """Send the initial message and store its reference."""
        embed = discord.Embed(
            title="Blackjack",
            description=(
                f"Your first card: {self.bj_game.hand_to_str(self.player_hand)} "
                f"({self.player_value})"
            ),
            color=discord.Colour.blurple(),
        )
        embed.add_field(
            name="Bet",
            value=(
                f"{self.countryball.description(include_emoji=True, bot=self.bot, is_trade=False)}"
            ),
            inline=False,
        )

        await interaction.response.send_message(embed=embed, view=self)
        self.message = await interaction.original_response()

    @button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: Button):
        self.player_hand.append(self.bj_game.deck.pop())
        self.player_value = self.bj_game.calculate_hand_value(self.player_hand)

        if self.player_value > 21:
            result = "You bust! You lose!"
            color = discord.Colour.red()
            reward = None
            await self.countryball.delete()
            await self.end_game(result, color, reward)
            return

        await self.update_embed("Hit! Your move.")

    @button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: Button):
        while self.ai_value < 17:
            self.ai_hand.append(self.bj_game.deck.pop())
            self.ai_value = self.bj_game.calculate_hand_value(self.ai_hand)

        result = ""
        color = discord.Colour.green()
        reward = None
        ball = await self.countryball.ball.first()

        if self.player_value > 21:
            result = "You bust! You lose!"
            color = discord.Colour.red()
            await self.countryball.delete()
        elif self.ai_value > 21:
            result = "The AI busts! You win!"
            color = discord.Colour.green()
            reward = f"You win your bet {settings.collectible_name} and a new instance!"
            await BallInstance.create(
                player=self.player,
                ball=ball,
                attack_bonus=random.randint(-20, 20),
                health_bonus=random.randint(-20, 20),
            )
        elif self.player_value > self.ai_value:
            result = "You win!"
            color = discord.Colour.green()
            reward = f"You win your bet {settings.collectible_name} and a new instance!"
            await BallInstance.create(
                player=self.player,
                ball=ball,
                attack_bonus=random.randint(-20, 20),
                health_bonus=random.randint(-20, 20),
            )
        elif self.player_value < self.ai_value:
            result = "You lose!"
            color = discord.Colour.red()
            await self.countryball.delete()
        else:
            result = "It's a draw!"
            color = discord.Colour.blurple()
            reward = f"{settings.collectible_name.title()} returned."

        await self.end_game(result, color, reward)

    async def end_game(self, result, color, reward):
        embed = discord.Embed(
            title="Blackjack Results",
            description=result,
            color=color,
        )
        embed.add_field(
            name="Your Hand",
            value=f"{self.bj_game.hand_to_str(self.player_hand)} ({self.player_value})",
            inline=False,
        )
        embed.add_field(
            name="AI's Hand",
            value=f"{self.bj_game.hand_to_str(self.ai_hand)} ({self.ai_value})",
            inline=False,
        )
        embed.add_field(
            name="Bet",
            value=f"{self.countryball.description(include_emoji=True, bot=self.bot, is_trade=False)}",
            inline=False,
        )
        if reward:
            embed.add_field(name="Reward", value=reward, inline=False)

        await self.message.edit(embed=embed, view=None)

    async def update_embed(self, title):
        """Updates the existing embed in the same message."""
        if not self.message:
            await self.send_initial_message()

        embed = discord.Embed(
            title=title,
            description="Make your move!",
            color=discord.Colour.blue(),
        )
        embed.add_field(
            name="Your Hand",
            value=f"{self.bj_game.hand_to_str(self.player_hand)} ({self.player_value})",
            inline=False,
        )
        embed.add_field(
            name="AI's Hand",
            value=f"{self.bj_game.hand_to_str(self.ai_hand)} ({self.ai_value})",
            inline=False,
        )
        embed.add_field(
            name="Bet",
            value=f"{self.countryball.description(include_emoji=True, bot=self.bot, is_trade=False)}",
            inline=False,
        )

        await self.message.edit(embed=embed, view=self)
