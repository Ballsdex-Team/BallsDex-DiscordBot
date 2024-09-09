import zipfile
from io import BytesIO
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from tortoise.expressions import Q

from ballsdex.core.models import BallInstance, DonationPolicy, MentionPolicy
from ballsdex.core.models import Player as PlayerModel
from ballsdex.core.models import PrivacyPolicy, Trade, TradeObject, balls
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
                "Setting updated, you will now receive all donated "
                f"{settings.plural_collectible_name} immediately."
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
    @app_commands.choices(
        policy=[
            app_commands.Choice(name="Accept all mentions", value=MentionPolicy.ALLOW),
            app_commands.Choice(name="Deny all mentions", value=MentionPolicy.DENY),
        ]
    )
    async def mention_policy(self, interaction: discord.Interaction, policy: MentionPolicy):
        """
        Set your mention policy.

        Parameters
        ----------
        policy: MentionPolicy
            The new policy for mentions
        """
        player, _ = await PlayerModel.get_or_create(discord_id=interaction.user.id)
        player.mention_policy = policy
        await player.save()
        await interaction.response.send_message(
            f"Your mention policy has been set to **{policy.name.lower()}**.", ephemeral=True
        )

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

    @app_commands.command()
    async def stats(self, interaction: discord.Interaction):
        """
        View your statistics in the bot!
        """
        await interaction.response.defer(thinking=True)
        player = await PlayerModel.get(discord_id=interaction.user.id).prefetch_related("balls")
        ball = await BallInstance.filter(player=player).prefetch_related("special")

        user = interaction.user
        bot_countryballs = {x: y.emoji_id for x, y in balls.items() if y.enabled}
        total_countryballs = len(bot_countryballs)
        owned_countryballs = set(
            x[0]
            for x in await player.balls.filter(ball__enabled=True)
            .distinct()
            .values_list("ball_id")
        )
        completion_percentage = f"{round(len(owned_countryballs) / total_countryballs * 100, 1)}%"
        caught_owned = [x for x in ball if x.trade_player is None]
        balls_owned = [x for x in ball]
        shiny = [x for x in ball if x.shiny is True]
        special = [x for x in ball if x.special is not None]
        trades = await Trade.filter(
            Q(player1__discord_id=interaction.user.id) | Q(player2__discord_id=interaction.user.id)
        ).count()

        embed = discord.Embed(
            title=f"**{user.display_name.title()}'s {settings.bot_name.title()} Stats**",
            color=discord.Color.blurple(),
        )
        embed.description = (
            "Here are your current statistics in the bot!\n\n"
            f"**Completion:** {completion_percentage}\n"
            f"**{settings.collectible_name.title()}s Owned:** {len(balls_owned)}\n"
            f"**Caught {settings.collectible_name.title()}s Owned**: {len(caught_owned)}\n"
            f"**Shiny {settings.collectible_name.title()}s:** {len(shiny)}\n"
            f"**Special {settings.collectible_name.title()}s:** {len(special)}\n"
            f"**Trades Completed:** {trades}"
        )
        embed.set_footer(text="Keep collecting and trading to improve your stats!")
        embed.set_thumbnail(url=user.display_avatar)  # type: ignore
        await interaction.followup.send(embed=embed)

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
