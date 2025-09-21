import discord
import random
import string
import logging
import re
import asyncio

from discord import app_commands
from discord.ext import commands
from typing import TYPE_CHECKING, List
from discord.ui import Button, View, Select

from ballsdex.settings import settings
from ballsdex.core.utils.transformers import BallTransform
from ballsdex.core.utils.logging import log_action
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.boss.cog")
FILENAME_RE = re.compile(r"^(.+)(\.\S+)$")

from ballsdex.core.models import (
    Ball,
    BallInstance,
    BlacklistedGuild,
    BlacklistedID,
    GuildConfig,
    Player,
    Trade,
    TradeObject,
    balls,
    specials,
)

class JoinButton(Button):
    def __init__(self, boss_cog):
        super().__init__(label="Join Boss Battle", style=discord.ButtonStyle.primary)
        self.boss_cog = boss_cog

    async def callback(self, interaction: discord.Interaction):
        if not self.boss_cog.boss_enabled:
            return await interaction.response.send_message("Boss is disabled", ephemeral=True)
        if [int(interaction.user.id), self.boss_cog.round] in self.boss_cog.usersinround:
            return await interaction.response.send_message("You have already joined the boss", ephemeral=True)
        if self.boss_cog.round != 0 and interaction.user.id not in self.boss_cog.users:
            return await interaction.response.send_message(
                "It is too late to join the boss, or you have died", ephemeral=True
            )
        if interaction.user.id in self.boss_cog.users:
            return await interaction.response.send_message(
                "You have already joined the boss", ephemeral=True
            )
        self.boss_cog.users.append(interaction.user.id)
        await interaction.response.send_message(
            "You have joined the Boss Battle!", ephemeral=True
        )
        # Notify the channel that a new user has joined the boss battle
        await interaction.channel.send(f"{interaction.user.mention} has joined the Boss Battle!")

class InventoryPaginator(View):
    def __init__(self, boss_cog, user_id: int, balls: List[BallInstance], page_size: int = 5):
        super().__init__(timeout=180)
        self.boss_cog = boss_cog
        self.user_id = user_id
        self.balls = balls
        self.page_size = page_size
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        start = self.current_page * self.page_size
        end = start + self.page_size
        current_balls = self.balls[start:end]

        # Add ball selection buttons
        for ball in current_balls:
            self.add_item(BallButton(self.boss_cog, ball))

        # Add navigation buttons
        if self.current_page > 0:
            self.add_item(PreviousPageButton(self))
        if end < len(self.balls):
            self.add_item(NextPageButton(self))

    async def send(self, interaction: discord.Interaction):
        start = self.current_page * self.page_size
        end = start + self.page_size
        current_balls = self.balls[start:end]
        description = "\n".join(
            f"{ball.description(short=True, include_emoji=True, bot=self.boss_cog.bot)}"
            for ball in current_balls
        )
        embed = discord.Embed(
            title="Your Inventory",
            description=description or "No balls available.",
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(embed=embed, view=self)


class PreviousPageButton(Button):
    def __init__(self, paginator: InventoryPaginator):
        super().__init__(label="Previous", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page -= 1
        self.paginator.update_buttons()
        await self.paginator.send(interaction)


class NextPageButton(Button):
    def __init__(self, paginator: InventoryPaginator):
        super().__init__(label="Next", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page += 1
        self.paginator.update_buttons()
        await self.paginator.send(interaction)


class BallButton(Button):
    def __init__(self, boss_cog, ball: BallInstance):
        super().__init__(label=f"{ball.ball.country}", style=discord.ButtonStyle.primary)
        self.boss_cog = boss_cog
        self.ball = ball
        self.clicked = False  # Add a state flag to track if the button has been clicked

    async def callback(self, interaction: discord.Interaction):
        if self.clicked:  # Prevent the callback from running multiple times
            return await interaction.response.send_message(
                "You have already selected a ball!", ephemeral=True
            )

        self.clicked = True  # Mark the button as clicked

        # Disable all buttons immediately to prevent further interaction
        for item in self.view.children:
            if isinstance(item, Button):
                item.disabled = True

        # Update the message to reflect the disabled buttons
        await interaction.message.edit(view=self.view)

        # Call the boss cog's select_ball method
        await self.boss_cog.select_ball(interaction, self.ball)

class BossView(View):
    def __init__(self, boss_cog):
        super().__init__(timeout=None)
        self.add_item(JoinButton(boss_cog))

@app_commands.guilds(*settings.admin_guild_ids)
class Boss(commands.GroupCog):
    """
    Boss commands.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.boss_enabled = False
        self.balls = []
        self.users = []
        self.usersdamage = []
        self.usersinround = []
        self.currentvalue = ("")
        self.bossHP = 40000
        self.picking = False
        self.round = 0
        self.attack = False
        self.bossattack = 0
        self.bossball = None
        self.bosswild = None
        self.user_balls = {}
        self.boss_channel_id = None
        self.ball_health = {}
        self.picked = False
        self.final_blow_player_id = None

    bossadmin = app_commands.Group(name="admin", description="admin commands for boss")

    @bossadmin.command(name="start")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def start(self, interaction: discord.Interaction, ball: BallTransform, hp_amount: int | None = None):
        """
        Start the boss
        """
        if self.boss_enabled:
            return await interaction.response.send_message(f"There is already an ongoing boss battle", ephemeral=True)
        self.bossHP = hp_amount if hp_amount is not None else 40000
        self.boss_channel_id = interaction.channel_id  # Store the channel ID

        def generate_random_name():
            source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
            return "".join(random.choices(source, k=15))

        extension = ball.collection_card.split(".")[-1]
        file_location = "." + ball.collection_card
        file_name = f"nt_{generate_random_name()}.{extension}"
        await interaction.response.send_message(
            f"# The boss battle has begun!\n-# HP: {self.bossHP}\nPlayers have 10 minutes to join!",
            file=discord.File(file_location, filename=file_name),
            view=BossView(self)
        )
        if ball:
            self.boss_enabled = True
            self.bossball = ball

            extension = ball.wild_card.split(".")[-1]
            file_location = "." + ball.wild_card
            file_name = f"nt_{generate_random_name()}.{extension}"
            self.bosswild = discord.File(file_location, filename=file_name)

        # Start the join timer
        await self.start_join_timer(interaction)

    async def start_join_timer(self, interaction: discord.Interaction):
        message = await interaction.channel.send("Players have 10 minutes to join the boss battle!")
        for i in range(600, 0, -1):
            minutes, seconds = divmod(i, 60)
            await message.edit(content=f"`{minutes:02}:{seconds:02}` remaining to join the boss battle!")
            await asyncio.sleep(1)  # 1 second
        if self.boss_enabled and not self.picking:
            await self.start_round(interaction)

    async def start_round(self, interaction: discord.Interaction):
        """
        Start a new round of the boss battle.
        """
        if not self.boss_enabled:
            return
    
        boss_channel = self.bot.get_channel(self.boss_channel_id)
        self.picking = True
        self.attack = random.randint(1, 10)  # Randomly pick attack or defend round
    
        if self.round == 0:
            # Send a message indicating the first round is starting
            await boss_channel.send("First round is starting...")
    
        if self.attack <= 3:  # 30% chance to attack
            await boss_channel.send("Starting `Attack` round...")
            await self._attack_round(interaction)
        else:
            await boss_channel.send("Starting `Defend` round...")
            await self._defend_round(interaction)
    
        # Start the round timer
        await self.start_round_timer(interaction)

    async def start_round_timer(self, interaction: discord.Interaction):
        boss_channel = self.bot.get_channel(1332995685481713687)
        message = await boss_channel.send("01:00 remaining in this round!")
        for i in range(60, 0, -1):
            minutes, seconds = divmod(i, 60)
            await message.edit(content=f"`{minutes:02}:{seconds:02}` remaining in this round!")
            await asyncio.sleep(1)  # 1 second
        if self.picking:
            await self._end_round(interaction)

    async def send_ball_selection(self, user_id: int):
        """
        Send the paginator for ball selection to the user.
        If the user does not select a ball within the timeout, a random ball is chosen and used.
        """
        if user_id in self.user_balls:
            return  # Ball selection menu already sent
    
        player = await Player.get(discord_id=user_id)
        self.user_balls[user_id] = await BallInstance.filter(player=player).prefetch_related("ball")
    
        if not self.user_balls[user_id]:
            user = await self.bot.fetch_user(user_id)
            return await user.send("You have no balls to select.")
    
        user = await self.bot.fetch_user(user_id)
        balls = list(self.user_balls[user_id])  # Convert QuerySet to a list of BallInstance objects
        paginator = InventoryPaginator(self, user_id, balls)  # Pass the list of balls
        start = paginator.current_page * paginator.page_size
        end = start + paginator.page_size
        current_balls = balls[start:end]
        description = "\n".join(
            f"{ball.description(short=True, include_emoji=True, bot=self.bot)}"
            for ball in current_balls
        )
        embed = discord.Embed(
            title="Your Inventory",
            description=description or "No balls available.",
            color=discord.Color.blue(),
        )
    
        try:
            # Send the ball selection menu to the user
            await user.send("Select a ball to use in the boss battle:", embed=embed, view=paginator)
    
            # Wait for the user to select a ball within the timeout period
            await asyncio.sleep(60)  # Timeout period (60 seconds)
    
            # If the user has not selected a ball, choose one randomly and use it
            if user_id not in self.user_balls or not isinstance(self.user_balls[user_id], BallInstance):
                random_ball = random.choice(balls)
                self.user_balls[user_id] = random_ball
                self.ball_health[user_id] = random_ball.health  # Store the health of the ball
                await user.send(
                    f"You did not select a ball in time. A random ball has been chosen for you: "
                    f"{random_ball.description(short=True, include_emoji=True, bot=self.bot)}"
                )
                # Use the randomly selected ball
                await self.select_ball_from_random(user_id, random_ball)
        except Exception as e:
            log.warning(f"Failed to send ball selection to user {user_id}: {e}")
            # Randomly select a ball for the user if an error occurs
            if balls:
                random_ball = random.choice(balls)
                self.user_balls[user_id] = random_ball
                self.ball_health[user_id] = random_ball.health  # Store the health of the ball
                log.info(f"Randomly selected ball {random_ball.ball.country} for user {user_id}")
                # Use the randomly selected ball
                await self.select_ball_from_random(user_id, random_ball)
            else:
                log.warning(f"User {user_id} has no balls to select.")
    
    async def select_ball_from_random(self, user_id: int, ball: BallInstance):
        """
        Handle the logic for using a randomly selected ball.
        """
        if user_id not in self.users:
            return  # User is not part of the boss battle
    
        # Check if the ball is already in use or invalid
        if ball in self.balls or any(ball.id == b.id for b in self.balls):
            log.warning(f"Randomly selected ball {ball.ball.country} is already in use.")
            return
    
        # Add the ball to the round
        self.balls.append(ball)
        self.usersinround.append([user_id, self.round])
        self.user_balls[user_id] = ball
        self.ball_health[user_id] = ball.health  # Store the health of the ball
    
        # Adjust stats if necessary
        ballattack = min(max(ball.attack, 0), 14000)  # Clamp attack between 0 and 14000
        ballhealth = min(max(ball.health, 0), 14000)  # Clamp health between 0 and 14000
    
        # Apply bonuses for special balls
        if "✨" in ball.description(short=True, include_emoji=True, bot=self.bot):
            ballattack += 1000
            ballhealth += 1000
    
        # Notify the boss channel
        boss_channel = self.bot.get_channel(self.boss_channel_id)
        await boss_channel.send(
            f"<@{user_id}> did not select a ball in time. A random ball has been chosen: "
            f"{ball.description(short=True, include_emoji=True, bot=self.bot)} "
            f"{ballattack} ATK {ballhealth} HP."
        )
    
        # Check if all players have picked a ball
        if len(self.usersinround) == len(self.users):
            await self._end_round(None)  # Pass None since interaction is not required

    async def select_ball(self, interaction: discord.Interaction, ball: BallInstance):
        """
        Handle ball selection from the dropdown menu.
        """
        if [int(interaction.user.id), self.round] in self.usersinround:
            return await interaction.response.send_message(
                f"You have already selected an {settings.collectible_name} for this round", ephemeral=True
            )
        if not self.boss_enabled:
            return await interaction.response.send_message("Boss is disabled", ephemeral=True)
        if not self.picking:
            return await interaction.response.send_message(f"It is not yet time to select an {settings.collectible_name}", ephemeral=True)
        if interaction.user.id not in self.users:
            return await interaction.response.send_message(
                "You have not Joined the Boss Battle, or you have died!", ephemeral=True
            )
        if not ball.is_tradeable:
            await interaction.response.send_message(
                f"You cannot use this {settings.collectible_name}.", ephemeral=True
            )
            return
        if ball in self.balls:
            return await interaction.response.send_message(
                f"You cannot select the same {settings.collectible_name} twice", ephemeral=True
            )
        if ball == None:
            return
        if any(ball.id == b.id for b in self.balls):
            return await interaction.response.send_message(
                f"You have already selected this {settings.collectible_name} in a previous round", ephemeral=True
            )
        self.balls.append(ball)
        self.usersinround.append([int(interaction.user.id), self.round])
        self.user_balls[interaction.user.id] = ball
        self.ball_health[interaction.user.id] = ball.health  # Store the health of the ball
        if ball.attack > 14000:  # maximum and minimum atk and hp stats
            ballattack = 14000
        elif ball.attack < 0:
            ballattack = 0
        else:
            ballattack = ball.attack
        if ball.health > 14000:
            ballhealth = 14000
        elif ball.health < 0:
            ballhealth = 0
        else:
            ballhealth = ball.health
        messageforuser = f"{ball.description(short=True, include_emoji=True, bot=self.bot)} has been selected for this round, with {ballattack} ATK and {ballhealth} HP"
        if "✨" in messageforuser:
            messageforuser = f"{ball.description(short=True, include_emoji=True, bot=self.bot)} has been selected for this round, with {ballattack}+1000 ATK and {ballhealth}+1000 HP"
            ballhealth += 1000
            ballattack += 1000
        else:
            pass
    
        await interaction.response.send_message(
            messageforuser, ephemeral=True
        )
    
        # Check if all players have picked a ball
        if len(self.usersinround) == len(self.users):
            await self._end_round(interaction)

    async def _attack_round(self, interaction: discord.Interaction, attack_amount: int | None = None):
        """
        Start a round where the Boss Attacks
        """
        boss_channel = self.bot.get_channel(1332995685481713687)
        self.bossattack = random.randint(50, 1000)
        if not self.boss_enabled:
            return await interaction.channel.send("Boss is disabled")
        if len(self.users) == 0:
            return await interaction.channel.send("There are not enough users to start the round")
        if self.bossHP <= 0:
            return await interaction.channel.send("The Boss is dead")
        self.round += 1

        def generate_random_name():
            source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
            return "".join(random.choices(source, k=15))
        
        extension = self.bossball.wild_card.split(".")[-1]
        file_location = "." + self.bossball.wild_card
        file_name = f"nt_{generate_random_name()}.{extension}"
        await boss_channel.send(
            (f"Round {self.round}\n# {self.bossball.country} is preparing to attack!"), file=discord.File(file_location, filename=file_name)
        )
        self.picking = True
        self.attack = True
        self.bossattack = random.randint(50, 1000)  # Set a random attack value between 1000 and 2000

        # Send ball selection to each user
        for user_id in self.users:
            await self.send_ball_selection(user_id)

    async def _defend_round(self, interaction: discord.Interaction):
        """
        Start a round where the Boss Defends
        """
        boss_channel = self.bot.get_channel(1332995685481713687)
        if not self.boss_enabled:
            return await interaction.channel.send("Boss is disabled")
        if len(self.users) == 0:
            return await interaction.channel.send("There are not enough users to start the round")
        if self.bossHP <= 0:
            return await interaction.channel.send("The Boss is dead")
        self.round += 1

        def generate_random_name():
            source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
            return "".join(random.choices(source, k=15))
        extension = self.bossball.wild_card.split(".")[-1]
        file_location = "." + self.bossball.wild_card
        file_name = f"nt_{generate_random_name()}.{extension}"
        await boss_channel.send(
            (f"Round {self.round}\n# {self.bossball.country} is preparing to defend!"), file=discord.File(file_location, filename=file_name)
        )
        if not self.picked:
            await interaction.channel.send(f"Use the dropdown menu to select your attacking {settings.collectible_name}.\nYour selected {settings.collectible_name}'s ATK will be used to attack.")
            self.picked = True
        self.picking = True
        self.attack = False

        # Send ball selection to each user
        for user_id in self.users:
            await self.send_ball_selection(user_id)

    async def _end_round(self, interaction: discord.Interaction):
        """
        End the current round
        """
        if not self.boss_enabled:
            if interaction:
                return await interaction.channel.send("Boss is disabled")
            return

        if not self.picking:
            if interaction:
                return await interaction.channel.send(
                    f"There are no ongoing rounds, use `/boss attack` or `/boss defend` to start one"
                )
            return

        self.picking = False
        boss_channel = self.bot.get_channel(self.boss_channel_id)
        self.currentvalue = ""  # Reset currentvalue at the start of the method
        self.final_blow_player_id = None
    
        if not self.attack:
            total_damage = 0  # Added to calculate total damage
            for user in self.users:
                ball = self.user_balls.get(user)
                if ball:
                    damage = random.randint(10, ball.attack)
                    total_damage += damage
                    self.bossHP -= damage
                    self.currentvalue += (f"<@{user}>'s {ball.description(short=True, include_emoji=True, bot=self.bot)} dealt {damage} damage!\n")
                    if self.bossHP <= 0:
                        self.final_blow_player_id = user  # Store the ID of the player who landed the final blow
                        break
            if int(self.bossHP) <= 0:
                await boss_channel.send(
                    f"{self.currentvalue}There is 0 HP remaining on the boss, the boss has been defeated!"
                )
                await self._conclude(interaction)
            else:
                end_message = await boss_channel.send(f"{self.currentvalue}There is {self.bossHP} HP remaining on the boss")
                thread = await end_message.create_thread(
                    name=f"Round {self.round}",
                    auto_archive_duration=60,
                )
                await thread.send(f"Round {self.round}")
        else:
            snapshotusers = self.users.copy()
            for user in snapshotusers:
                ball = self.user_balls.get(user)
                if ball:
                    if self.bossattack >= self.ball_health[user]:  # Use the stored health of the ball
                        self.users.remove(user)
                        self.currentvalue += (f"<@{user}>'s {ball.description(short=True, include_emoji=True, bot=self.bot)} had {self.ball_health[user]} HP and ***died!***\n")
                    else:
                        self.ball_health[user] -= self.bossattack  # Update the stored health of the ball
                        self.currentvalue += (f"<@{user}>'s {ball.description(short=True, include_emoji=True, bot=self.bot)} had {self.ball_health[user]} HP and ***survived!***\n")
                else:
                    self.currentvalue += (f"<@{user}> has not picked on time and ***died!***\n")
                    self.users.remove(user)
            if len(self.users) == 0:
                end_message = await boss_channel.send(f"The boss has dealt {self.bossattack} damage!\n{self.currentvalue}The boss has won!")
                thread = await end_message.create_thread(
                    name=f"Round {self.round}",
                    auto_archive_duration=60,
                )
                await thread.send(f"Round {self.round}")
                await self._conclude(interaction)
            else:
                end_message = await boss_channel.send(f"The boss has dealt {self.bossattack} damage!\n{self.currentvalue}")
                thread = await end_message.create_thread(
                    name=f"Round {self.round}",
                    auto_archive_duration=60,
                )
                await thread.send(f"Round {self.round}")
        self.currentvalue = ""  # Reset currentvalue after sending the message
        if self.boss_enabled:
            await self.start_round(interaction)

    @bossadmin.command(name="start_attack")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def start_attack(self, interaction: discord.Interaction):
        """
        Manually start an attack round
        """
        if not self.boss_enabled:
            return await interaction.response.send_message("Boss is disabled", ephemeral=True)
        if self.picking:
            return await interaction.response.send_message("There is already an ongoing round", ephemeral=True)
        await self._attack_round(interaction)

    @bossadmin.command(name="start_defend")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def start_defend(self, interaction: discord.Interaction):
        """
        Manually start a defend round
        """
        if not self.boss_enabled:
            return await interaction.response.send_message("Boss is disabled", ephemeral=True)
        if self.picking:
            return await interaction.response.send_message("There is already an ongoing round", ephemeral=True)
        await self._defend_round(interaction)

    @bossadmin.command(name="end_round")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def end_round_command(self, interaction: discord.Interaction):
        """
        End the current round
        """
        await self._end_round(interaction)

    @bossadmin.command(name="stats")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def stats(self, interaction: discord.Interaction):
        """
        See current stats of the boss
        """
        with open("stats.txt", "w") as file:
            file.write(f"Boss:{self.bossball}\nCurrentValue:{self.currentvalue}\nUsers:{self.users}\n\nUsersDamage:{self.usersdamage}\n\nBalls:{self.balls}\n\nUsersInRound:{self.usersinround}")
        with open("stats.txt", "rb") as file:
            return await interaction.response.send_message(file=discord.File(file, "stats.txt"), ephemeral=True)
        
    async def _conclude(self, interaction: discord.Interaction, do_not_reward: bool | None = False):
        """
        Finish the boss, conclude the Winner
        """
        self.picking = False
        self.boss_enabled = False
        boss_channel = self.bot.get_channel(1332995685481713687)
        # Check if the boss has been defeated
        if self.bossHP > 0:
            self.reset_boss_state()
            return await boss_channel.send("The boss has not been defeated. No rewards will be given.")

        test = self.usersdamage
        test2 = []
        total = ("")
        totalnum = []
        bosswinner = self.final_blow_player_id if self.final_blow_player_id else 0
        highest = 0
        if bosswinner == 0:
            self.reset_boss_state()
            return await boss_channel.send(f"BOSS HAS CONCLUDED\nThe boss has won the Boss Battle!")
        if not do_not_reward:
            player, created = await Player.get_or_create(discord_id=bosswinner)
            log.debug("Specials dictionary contents: %s", specials)
            special = next((x for x in specials.values() if x.name == "Boss"), None)
            if special is None:
                self.reset_boss_state()
                return await interaction.followup.send("Error: 'Boss' special not found.", ephemeral=True)
            instance = await BallInstance.create(
                ball=self.bossball,
                player=player,
                shiny=False,
                special=special,
                attack_bonus=0,
                health_bonus=0,
            )
            await boss_channel.send(
                f"BOSS HAS CONCLUDED.\n{total}\n<@{bosswinner}> has won the Boss Battle!\n\n"
                f"`{self.bossball.country}` {settings.collectible_name} was successfully given to *<@{bosswinner}>*.\n"
                f"ATK:`0` • Special: `Boss`\n"
                f"HP:`0` • Shiny: `None`"
            )
            await log_action(
                f"`BOSS REWARDS` gave {settings.collectible_name} {self.bossball.country} to *<@{bosswinner}>*"
                f"Special=Boss ATK=0 "
                f"HP=0 shiny=None",
                self.bot,
            )
        else:
            await boss_channel.send(f"BOSS HAS CONCLUDED.\n{total}\n<@{bosswinner}> has won the Boss Battle!\n\n")
        self.reset_boss_state()

    @bossadmin.command(name="conclude")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def conclude(self, interaction: discord.Interaction, do_not_reward: bool | None = False):
        """
        Finish the boss, conclude the Winner
        """
        self.picking = False
        self.boss_enabled = False
        boss_channel = self.bot.get_channel(1332995685481713687)
        # Check if the boss has been defeated
        if self.bossHP > 0:
            self.reset_boss_state()
            return await boss_channel.send("The boss has not been defeated. No rewards will be given.")

        
        test = self.usersdamage
        test2 = []
        total = ("")
        totalnum = []
        for i in range(len(test)):
            if test[i][0] not in test2 and test[i][0] in self.users:
                temp = 0
                tempvalue = test[i][0]
                test2.append(tempvalue)
                for j in range(len(test)):
                    if test[j][0] == tempvalue:
                        temp += test[j][1]
                total += ("<@" + str(tempvalue) + "> has dealt a total of " + str(temp) + " damage!\n")
                totalnum.append([tempvalue, temp])
        bosswinner = 0
        highest = 0
        for k in range(len(totalnum)):
            if totalnum[k][1] > highest:
                highest = totalnum[k][1]
                bosswinner = totalnum[k][0]
        if bosswinner == 0:
            self.reset_boss_state()
            return await boss_channel.send(f"BOSS HAS CONCLUDED\nThe boss has won the Boss Battle!")
        if not do_not_reward:
            await interaction.response.defer(thinking=True)
            player, created = await Player.get_or_create(discord_id=bosswinner)
            log.debug("Specials dictionary contents: %s", specials)
            special = next((x for x in specials.values() if x.name == "Boss"), None)
            if special is None:
                self.reset_boss_state()
                return await interaction.followup.send("Error: 'Boss' special not found.", ephemeral=True)
            instance = await BallInstance.create(
                ball=self.bossball,
                player=player,
                shiny=False,
                special=special,
                attack_bonus=random.randint(-20, 20),
                health_bonus=random.randint(-20, 20),
            )
            await boss_channel.send(
                f"BOSS HAS CONCLUDED.\n{total}\n<@{bosswinner}> has won the Boss Battle!\n\n"
                f"`{self.bossball.country}` {settings.collectible_name} was successfully given to *<@{bosswinner}>*.\n"
                f"ATK:`0` • Special: `Boss`\n"
                f"HP:`0` • Shiny: `None`"
            )
            await log_action(
                f"`BOSS REWARDS` gave {settings.collectible_name} {self.bossball.country} to *<@{bosswinner}>*"
                f"Special=Boss ATK=0 "
                f"HP=0 shiny=None",
                self.bot,
            )
        else:
            await boss_channel.send(f"BOSS HAS CONCLUDED.\n{total}\n<@{bosswinner}> has won the Boss Battle!\n\n")
        self.reset_boss_state()

    def reset_boss_state(self):
        """
        Reset the state of the boss battle.
        """
        self.boss_enabled = False
        self.balls = []
        self.users = []
        self.usersdamage = []
        self.usersinround = []
        self.currentvalue = ("")
        self.bossHP = 40000
        self.picking = False
        self.round = 0
        self.attack = False
        self.bossattack = 0
        self.bossball = None
        self.bosswild = None
        self.user_balls = {}
        self.boss_channel_id = None
        self.ball_health = {}
        self.picked = False