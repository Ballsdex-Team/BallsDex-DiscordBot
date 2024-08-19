import zipfile
from io import BytesIO
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from tortoise.expressions import Q

from ballsdex.core.models import (
    BallInstance,
    DonationPolicy,
    Friendship,
    Player as PlayerModel,
    PrivacyPolicy,
    Trade,
    TradeObject,
)
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Player(commands.GroupCog):
    """
    Manage your account settings.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        if not self.bot.intents.members:
            self.__cog_app_commands_group__.get_command("privacy").parameters[  # type: ignore
                0
            ]._Parameter__parent.choices.pop()  # type: ignore

    friends = app_commands.Group(name="friends", description="Friend commands")

    @app_commands.command()
    @app_commands.choices(
        policy=[
            app_commands.Choice(name="Open Inventory", value=PrivacyPolicy.ALLOW),
            app_commands.Choice(name="Private Inventory", value=PrivacyPolicy.DENY),
            app_commands.Choice(name="Same Server", value=PrivacyPolicy.SAME_SERVER),
        ]
    )
    async def privacy(self, interaction: discord.Interaction, policy: PrivacyPolicy):
        """
        Set your privacy policy.
        """
        if policy == PrivacyPolicy.SAME_SERVER and not self.bot.intents.members:
            await interaction.response.send_message(
                "I need the `members` intent to use this policy.", ephemeral=True
            )
            return
        player, _ = await PlayerModel.get_or_create(discord_id=interaction.user.id)
        player.privacy_policy = policy
        await player.save()
        await interaction.response.send_message(
            f"Your privacy policy has been set to **{policy.name}**.", ephemeral=True
        )

    @app_commands.command()
    @app_commands.choices(
        policy=[
            app_commands.Choice(name="Accept all donations", value=DonationPolicy.ALWAYS_ACCEPT),
            app_commands.Choice(
                name="Request your approval first", value=DonationPolicy.REQUEST_APPROVAL
            ),
            app_commands.Choice(name="Deny all donations", value=DonationPolicy.ALWAYS_DENY),
        ]
    )
    async def donation_policy(
        self, interaction: discord.Interaction, policy: app_commands.Choice[int]
    ):
        """
        Change how you want to receive donations from /balls give

        Parameters
        ----------
        policy: DonationPolicy
            The new policy for accepting donations
        """
        player, _ = await PlayerModel.get_or_create(discord_id=interaction.user.id)
        player.donation_policy = DonationPolicy(policy.value)
        if policy.value == DonationPolicy.ALWAYS_ACCEPT:
            await interaction.response.send_message(
                f"Setting updated, you will now receive all donated {settings.collectible_name}s "
                "immediately."
            )
        elif policy.value == DonationPolicy.REQUEST_APPROVAL:
            await interaction.response.send_message(
                "Setting updated, you will now have to approve donation requests manually."
            )
        elif policy.value == DonationPolicy.ALWAYS_DENY:
            await interaction.response.send_message(
                "Setting updated, it is now impossible to use "
                f"`/{settings.players_group_cog_name} give` with "
                "you. It is still possible to perform donations using the trade system."
            )
        else:
            await interaction.response.send_message("Invalid input!")
            return
        await player.save()  # do not save if the input is invalid

    @app_commands.command()
    async def delete(self, interaction: discord.Interaction):
        """
        Delete your player data.
        """
        view = ConfirmChoiceView(interaction)
        await interaction.response.send_message(
            "Are you sure you want to delete your player data?", view=view, ephemeral=True
        )
        await view.wait()
        if view.value is None or not view.value:
            return
        player, _ = await PlayerModel.get_or_create(discord_id=interaction.user.id)
        await player.delete()

    @friends.command()
    async def add(self, interaction: discord.Interaction, user: discord.User):
        """
        Add another user as a friend.

        Parameters
        ----------
        user: discord.User
            The user you want to add as a friend.
        """
        player1, _ = await PlayerModel.get_or_create(discord_id=interaction.user.id)
        player2, _ = await PlayerModel.get_or_create(discord_id=user.id)

        if player1 == player2:
            await interaction.response.send_message(
                "You cannot add yourself as a friend.", ephemeral=True
            )
            return
        if user.bot:
            await interaction.response.send_message("You cannot add a bot.", ephemeral=True)
            return
        if player2 in self.bot.blacklist:
            await interaction.response.send_message(
                "You cannot add a blacklisted user.", ephemeral=True
            )
            return

        existing_friendship = await Friendship.filter(
            (Q(player1=player1) & Q(player2=player2)) | (Q(player1=player2) & Q(player2=player1))
        ).first()

        if existing_friendship:
            await interaction.response.send_message(
                "You are already friends with this user.", ephemeral=True
            )
            return

        await Friendship.create(player1=player1, player2=player2)
        await interaction.response.send_message(
            f"{user.mention} has been added as a friend!", ephemeral=True
        )

    @friends.command()
    async def remove(self, interaction: discord.Interaction, user: discord.User):
        """
        Remove a friend.

        Parameters
        ----------
        user: discord.User
            The user you want to remove as a friend.
        """
        player1, _ = await PlayerModel.get_or_create(discord_id=interaction.user.id)
        player2, _ = await PlayerModel.get_or_create(discord_id=user.id)

        if player1 == player2:
            await interaction.response.send_message(
                "You cannot remove yourself as a friend.", ephemeral=True
            )
            return
        if user.bot:
            await interaction.response.send_message("You cannot remove a bot.", ephemeral=True)
            return

        existing_friendship = await Friendship.filter(
            (Q(player1=player1) & Q(player2=player2)) | (Q(player1=player2) & Q(player2=player1))
        ).exists()

        if not existing_friendship:
            await interaction.response.send_message(
                "You are not friends with this user.", ephemeral=True
            )
            return

        await Friendship.filter(
            (Q(player1=player1) & Q(player2=player2)) | (Q(player1=player2) & Q(player2=player1))
        ).delete()
        await interaction.response.send_message(
            f"{user.mention} has been removed as a friend.", ephemeral=True
        )

    @app_commands.command()
    @app_commands.choices(
        type=[
            app_commands.Choice(name=settings.collectible_name.title(), value="balls"),
            app_commands.Choice(name="Trades", value="trades"),
            app_commands.Choice(name="All", value="all"),
        ]
    )
    async def export(self, interaction: discord.Interaction, type: str):
        """
        Export your player data.
        """
        player = await PlayerModel.get_or_none(discord_id=interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                "You don't have any player data to export.", ephemeral=True
            )
            return
        await interaction.response.defer()
        files = []
        if type == "balls":
            data = await get_items_csv(player)
            filename = f"{interaction.user.id}_{settings.collectible_name}.csv"
            data.filename = filename  # type: ignore
            files.append(data)
        elif type == "trades":
            data = await get_trades_csv(player)
            filename = f"{interaction.user.id}_trades.csv"
            data.filename = filename  # type: ignore
            files.append(data)
        elif type == "all":
            balls = await get_items_csv(player)
            trades = await get_trades_csv(player)
            balls_filename = f"{interaction.user.id}_{settings.collectible_name}.csv"
            trades_filename = f"{interaction.user.id}_trades.csv"
            balls.filename = balls_filename  # type: ignore
            trades.filename = trades_filename  # type: ignore
            files.append(balls)
            files.append(trades)
        else:
            await interaction.followup.send("Invalid input!", ephemeral=True)
            return
        zip_file = BytesIO()
        with zipfile.ZipFile(zip_file, "w") as z:
            for file in files:
                z.writestr(file.filename, file.getvalue())
        zip_file.seek(0)
        if zip_file.tell() > 25_000_000:
            await interaction.followup.send(
                "Your data is too large to export."
                "Please contact the bot support for more information.",
                ephemeral=True,
            )
            return
        files = [discord.File(zip_file, "player_data.zip")]
        try:
            await interaction.user.send("Here is your player data:", files=files)
            await interaction.followup.send(
                "Your player data has been sent via DMs.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I couldn't send the player data to you in DM. "
                "Either you blocked me or you disabled DMs in this server.",
                ephemeral=True,
            )


async def get_items_csv(player: PlayerModel) -> BytesIO:
    """
    Get a CSV file with all items of the player.
    """
    balls = await BallInstance.filter(player=player).prefetch_related(
        "ball", "trade_player", "special"
    )
    txt = (
        f"id,hex id,{settings.collectible_name},catch date,trade_player"
        ",special,shiny,attack,attack bonus,hp,hp_bonus\n"
    )
    for ball in balls:
        txt += (
            f"{ball.id},{ball.id:0X},{ball.ball.country},{ball.catch_date},"  # type: ignore
            f"{ball.trade_player.discord_id if ball.trade_player else 'None'},{ball.special},"
            f"{ball.shiny},{ball.attack},{ball.attack_bonus},{ball.health},{ball.health_bonus}\n"
        )
    return BytesIO(txt.encode("utf-8"))


async def get_trades_csv(player: PlayerModel) -> BytesIO:
    """
    Get a CSV file with all trades of the player.
    """
    trade_history = (
        await Trade.filter(Q(player1=player) | Q(player2=player))
        .order_by("date")
        .prefetch_related("player1", "player2")
    )
    txt = "id,date,player1,player2,player1 received,player2 received\n"
    for trade in trade_history:
        player1_items = await TradeObject.filter(
            trade=trade, player=trade.player1
        ).prefetch_related("ballinstance")
        player2_items = await TradeObject.filter(
            trade=trade, player=trade.player2
        ).prefetch_related("ballinstance")
        txt += (
            f"{trade.id},{trade.date},{trade.player1.discord_id},{trade.player2.discord_id},"
            f"{','.join([i.ballinstance.to_string() for i in player2_items])},"  # type: ignore
            f"{','.join([i.ballinstance.to_string() for i in player1_items])}\n"  # type: ignore
        )
    return BytesIO(txt.encode("utf-8"))
