import discord, asyncio
from discord import app_commands
from discord.ext import commands

from ballsdex.core.models import (
    Ball,
    BallInstance,
    Player,
    Special,
    PrivacyPolicy,
)
from ballsdex.core.utils.transformers import BallEnabledTransform
from tortoise.exceptions import DoesNotExist
from ballsdex.packages.balls.cog import inventory_privacy
from ballsdex.core.models import PrivacyPolicy

class Shop(commands.GroupCog, group_name="shop"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot  # Store the bot instance
        super().__init__()

    @app_commands.command()
    async def balance(self, interaction: discord.Interaction, user: discord.User | None = None):
        """
        Check your coin balance or another user's balance.
        """
        user_obj = user or interaction.user
        try:
            player = await Player.get(discord_id=user_obj.id)
        except DoesNotExist:
            if user_obj == interaction.user:
                await interaction.response.send_message(
                    "You don't have a balance yet.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"{user_obj.name} doesn't have a balance yet.", ephemeral=True
                )
            return

        # Check privacy settings if viewing another user's balance
        if user and user != interaction.user:
            if player.privacy_policy == PrivacyPolicy.DENY:
                await interaction.response.send_message(
                    "This user has set their balance to private.", ephemeral=False
                )
                return
            elif player.privacy_policy == PrivacyPolicy.SAME_SERVER:
                if not interaction.guild or interaction.guild.get_member(user_obj.id) is None:
                    await interaction.response.send_message(
                        "This user has set their balance to be visible only to members of the same server.",
                        ephemeral=False,
                    )
                    return

        embed = discord.Embed(
            title=f"{user_obj.name}'s Balance" if user else "Your Balance",
            description=f"Coins: **{player.coins}**",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command()
    async def view(self, interaction: discord.Interaction):
        '''
        View the shop.
        '''
        class BuyModal(discord.ui.Modal, title="Buy Item"):
            item_id = discord.ui.TextInput(
                label="Enter the item ID you want to buy:",
                placeholder="e.g., 1",
                required=True,
            )

            def __init__(self, player):
                super().__init__()
                self.player = player

            async def on_submit(self, interaction: discord.Interaction):
                item_id = self.item_id.value.strip()

                if item_id == "1":  # Basic Box I
                    price = 500

                    if self.player.coins >= price:
                        self.player.coins -= price
                        await self.player.save()

                        # Exclude T1-T19 (use rarity >= 0.0074 for T19+)
                        eligible_balls = await Ball.filter(rarity__gte=0.0074)
                        import random
                        received_balls = random.sample(eligible_balls, k=3)

                        # Give balls to player
                        ball_names = []
                        for ball in received_balls:
                            await BallInstance.create(
                                ball=ball,
                                player=self.player,
                                health_bonus=random.randint(-20, 20),
                                attack_bonus=random.randint(-20, 20),
                                defense_bonus=0,
                            )
                            ball_names.append(ball.country)
                        await interaction.response.send_message(
                            f"You bought a `Basic Box I` for `{price}` coins! Opening the box...\n"
                            f"You received: **{', '.join(ball_names)}**",
                            ephemeral=False,
                        )
                    else:
                        await interaction.response.send_message(
                            "You don't have enough coins to buy this item.",
                            ephemeral=True,
                        )
                elif item_id == "2":  # Basic Box II
                    price = 750

                    if self.player.coins >= price:
                        self.player.coins -= price
                        await self.player.save()

                        # Exclude T1-T19 (use rarity >= 0.0074 for T19+)
                        eligible_balls = await Ball.filter(rarity__gte=0.0074)
                        import random
                        received_balls = random.sample(eligible_balls, k=5)

                        # Give balls to player
                        ball_names = []
                        for ball in received_balls:
                            await BallInstance.create(
                                ball=ball,
                                player=self.player,
                                health_bonus=random.randint(-20, 20),
                                attack_bonus=random.randint(-20, 20),
                                defense_bonus=0,
                            )
                            ball_names.append(ball.country)
                        await interaction.response.send_message(
                            f"You bought a `Basic Box II` for `{price}` coins! Opening the box...\n"
                            f"You received: **{', '.join(ball_names)}**",
                            ephemeral=False,
                        )
                    else:
                        await interaction.response.send_message(
                            "You don't have enough coins to buy this item.",
                            ephemeral=True,
                        )
                elif item_id == "3":  # Basic Box III
                    price = 1000

                    if self.player.coins >= price:
                        self.player.coins -= price
                        await self.player.save()

                        # Exclude T1-T19 (use rarity >= 0.0074 for T19+)
                        eligible_balls = await Ball.filter(rarity__gte=0.0074)
                        import random
                        received_balls = random.sample(eligible_balls, k=7)

                        # Give balls to player
                        ball_names = []
                        for ball in received_balls:
                            await BallInstance.create(
                                ball=ball,
                                player=self.player,
                                health_bonus=random.randint(-20, 20),
                                attack_bonus=random.randint(-20, 20),
                                defense_bonus=0,
                            )
                            ball_names.append(ball.country)
                        await interaction.response.send_message(
                            f"You bought a `Basic Box III` for `{price}` coins! Opening the box...\n"
                            f"You received: **{', '.join(ball_names)}**",
                            ephemeral=False,
                        )
                    else:
                        await interaction.response.send_message(
                            "You don't have enough coins to buy this item.",
                            ephemeral=True,
                        )
                elif item_id == "4":  # Deluxe Box
                    price = 750

                    if self.player.coins >= price:
                        self.player.coins -= price
                        await self.player.save()

                        # Exclude T1-T12 (use rarity >= 0.02 for T12+)
                        eligible_balls = await Ball.filter(rarity__gte=0.0061)
                        import random
                        received_balls = random.sample(eligible_balls, k=5)

                        # Give balls to player
                        ball_names = []
                        for ball in received_balls:
                            await BallInstance.create(
                                ball=ball,
                                player=self.player,
                                health_bonus=random.randint(-20, 20),
                                attack_bonus=random.randint(-20, 20),
                                defense_bonus=0,
                            )
                            ball_names.append(ball.country)
                        await interaction.response.send_message(
                            f"You bought a `Deluxe Box` for `{price}` coins! Opening the box...\n"
                            f"You received: **{', '.join(ball_names)}**",
                            ephemeral=False,
                        )
                    else:
                        await interaction.response.send_message(
                            "You don't have enough coins to buy this item.",
                            ephemeral=True,
                        )
                elif item_id == "5":  # Premium Box
                    price = 1250

                    if self.player.coins >= price:
                        self.player.coins -= price
                        await self.player.save()

                        # Exclude T1-T12 (use rarity >= 0.02 for T12+)
                        eligible_balls = await Ball.filter(rarity__gte=0.0061)
                        import random
                        received_balls = random.sample(eligible_balls, k=7)

                        # Give balls to player
                        ball_names = []
                        for ball in received_balls:
                            await BallInstance.create(
                                ball=ball,
                                player=self.player,
                                health_bonus=random.randint(-20, 20),
                                attack_bonus=random.randint(-20, 20),
                                defense_bonus=0,
                            )
                            ball_names.append(ball.country)
                        await interaction.response.send_message(
                            f"You bought a `Premium Box` for `{price}` coins! Opening the box...\n"
                            f"You received: **{', '.join(ball_names)}**",
                            ephemeral=False,
                        )
                    else:
                        await interaction.response.send_message(
                            "You don't have enough coins to buy this item.",
                            ephemeral=True,
                        )
                elif item_id == "6":  # Big Box
                    price = 1500

                    if self.player.coins >= price:
                        self.player.coins -= price
                        await self.player.save()

                        # Exclude T1-T12 (use rarity >= 0.02 for T12+)
                        eligible_balls = await Ball.filter(rarity__gte=0.0061)
                        import random
                        received_balls = random.sample(eligible_balls, k=10)

                        # Give balls to player
                        ball_names = []
                        for ball in received_balls:
                            await BallInstance.create(
                                ball=ball,
                                player=self.player,
                                health_bonus=random.randint(-20, 20),
                                attack_bonus=random.randint(-20, 20),
                                defense_bonus=0,
                            )
                            ball_names.append(ball.country)
                        await interaction.response.send_message(
                            f"You bought a `Big Box` for `{price}` coins! Opening the box...\n"
                            f"You received: **{', '.join(ball_names)}**",
                            ephemeral=False,
                        )
                    else:
                        await interaction.response.send_message(
                            "You don't have enough coins to buy this item.",
                            ephemeral=True,
                        )
                elif item_id == "7":  # Coin Pack
                    price = 1000

                    if self.player.coins >= price:
                        self.player.coins -= price
                        await self.player.save()

                        import random
                        coins_received = random.randint(100, 2000)
                        self.player.coins += coins_received
                        await self.player.save()

                        await interaction.response.send_message(
                            f"You bought a `Coin Pack` for `{price}` coins!\n"
                            f"You received: **{coins_received}** coins!",
                            ephemeral=False,
                        )
                    else:
                        await interaction.response.send_message(
                            "You don't have enough coins to buy this item.",
                            ephemeral=True,
                        )
                elif item_id == "8":  # Master Box
                    price = 5000

                    if self.player.coins >= price:
                        self.player.coins -= price
                        await self.player.save()

                        # Select random balls with rarity in the given list
                        rarity_list = [0.0064, 0.0061, 0.0048, 0.0038, 0.0030, 0.0026, 0.0020]
                        eligible_balls = await Ball.filter(rarity__in=rarity_list)
                        import random
                        received_ball = random.choice(eligible_balls)

                        # Give ball to player
                        await BallInstance.create(
                            ball=received_ball,
                            player=self.player,
                            health_bonus=random.randint(-20, 20),
                            attack_bonus=random.randint(-20, 20),
                            defense_bonus=0,
                        )
                        await interaction.response.send_message(
                            f"You bought a `Master Box` for `{price}` coins! Opening the box...\n"
                            f"You received: **{received_ball.country}**",
                            ephemeral=False,
                        )
                    else:
                        await interaction.response.send_message(
                            "You don't have enough coins to buy this item.",
                            ephemeral=True,
                        )
                elif item_id == "9":  # Pro Box
                    price = 7500

                    if self.player.coins >= price:
                        self.player.coins -= price
                        await self.player.save()

                        # Select random balls with rarity in the given list
                        rarity_list = [0.0048, 0.0038, 0.0030, 0.0026, 0.0020]
                        eligible_balls = await Ball.filter(rarity__in=rarity_list)
                        import random
                        received_ball = random.choice(eligible_balls)

                        # Give ball to player
                        await BallInstance.create(
                            ball=received_ball,
                            player=self.player,
                            health_bonus=random.randint(-20, 20),
                            attack_bonus=random.randint(-20, 20),
                            defense_bonus=0,
                        )
                        await interaction.response.send_message(
                            f"You bought a `Pro Box` for `{price}` coins! Opening the box...\n"
                            f"You received: **{received_ball.country}**",
                            ephemeral=False,
                        )
                    else:
                        await interaction.response.send_message(
                            "You don't have enough coins to buy this item.",
                            ephemeral=True,
                        )
                else:
                    await interaction.response.send_message(
                        "Invalid item ID. Please try again.",
                        ephemeral=True,
                    )

        class BuyButton(discord.ui.View):
            def __init__(self, player):
                super().__init__()
                self.player = player

            @discord.ui.button(label="Buy", style=discord.ButtonStyle.green)
            async def buy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.send_modal(BuyModal(self.player))

        player, _ = await Player.get_or_create(discord_id=interaction.user.id)

        embed = discord.Embed(
            title="Shop",
            description="Use buttons to navigate and perform actions.",
            color=discord.Color.gold()
        )
        embed.add_field(name="[1] Basic Box I", value="3 random balls, all rarities excluding T1-T19 \nPrice: **500** Coins", inline=False)
        embed.add_field(name="[2] Basic Box II", value="5 random balls, all rarities excluding T1-T19 \nPrice: **750** Coins", inline=False)
        embed.add_field(name="[3] Basic Box III", value="7 random balls, all rarities excluding T1-T19 \nPrice: **1000** Coins", inline=False)
        embed.add_field(name="[4] Deluxe Box", value="5 random balls, all rarities excluding T1-T12\nPrice: **750** Coins", inline=False)
        embed.add_field(name="[5] Premium Box", value="7 random balls, all rarities excluding T1-T12\nPrice: **1250** Coins", inline=False)
        embed.add_field(name="[6] Big Box", value="10 random balls, all rarities excluding T1-T12\nPrice: **1500** Coins", inline=False)
        embed.add_field(name="[7] Coin Pack", value="Gives 100-2000 coins\nPrice: **1000** Coins", inline=False)
        embed.add_field(name="[8] Master Box", value="1 random ball from T1-T13\nPrice: **5000** Coins", inline=False)
        embed.add_field(name="[9] Pro Box", value="1 random ball from T1-T7\nPrice: **7500** Coins", inline=False)

        embed.add_field(name="[#] Item Name", value="Description\nPrice: **X** Coins", inline=False)
        await interaction.response.send_message(embed=embed, view=BuyButton(player), ephemeral=False)