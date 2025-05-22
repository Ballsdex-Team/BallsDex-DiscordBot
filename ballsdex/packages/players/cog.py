import zipfile
from io import BytesIO
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import format_dt
from django.db.models import Q

from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.enums import DONATION_POLICY_MAP, FRIEND_POLICY_MAP, MENTION_POLICY_MAP, PRIVATE_POLICY_MAP
from ballsdex.core.utils.enums import TRADE_COOLDOWN_POLICY_MAP as TRADE_POLICY_MAP
from ballsdex.core.utils.menus import FieldPageSource, Menu
from ballsdex.settings import settings
from bd_models.enums import DonationPolicy, FriendPolicy, MentionPolicy, PrivacyPolicy, TradeCooldownPolicy
from bd_models.models import BallInstance, Block, Friendship, Trade, TradeObject, balls
from bd_models.models import Player as PlayerModel

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Player(commands.GroupCog):
    """
    Manage your account settings.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.active_friend_requests = {}
        if not self.bot.intents.members and self.__cog_app_commands_group__:
            privacy_command = self.__cog_app_commands_group__.get_command("privacy")
            if privacy_command:
                privacy_command.parameters[0]._Parameter__parent.choices.pop()  # type: ignore

    friend = app_commands.Group(name="friend", description="Friend commands")
    blocked = app_commands.Group(name="block", description="Block commands")
    policy = app_commands.Group(name="policy", description="Policy commands")
    money = app_commands.Group(name="money", description="Money commands")

    @policy.command()
    @app_commands.choices(
        policy=[
            app_commands.Choice(name="Open Inventory", value=PrivacyPolicy.ALLOW),
            app_commands.Choice(name="Private Inventory", value=PrivacyPolicy.DENY),
            app_commands.Choice(name="Friends Only", value=PrivacyPolicy.FRIENDS),
            app_commands.Choice(name="Same Server", value=PrivacyPolicy.SAME_SERVER),
        ]
    )
    async def privacy(self, interaction: discord.Interaction["BallsDexBot"], policy: PrivacyPolicy):
        """
        Set your privacy policy.

        Parameters
        ----------
        policy: PrivacyPolicy
            The new privacy policy to choose.
        """
        player, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)
        if policy == PrivacyPolicy.SAME_SERVER and not self.bot.intents.members:
            await interaction.response.send_message("I need the `members` intent to use this policy.", ephemeral=True)
            return
        player.privacy_policy = PrivacyPolicy(policy.value)
        await player.asave()
        await interaction.response.send_message(
            f"Your privacy policy has been set to **{policy.name}**.", ephemeral=True
        )

    @policy.command()
    @app_commands.choices(
        policy=[
            app_commands.Choice(name="Accept all donations", value=DonationPolicy.ALWAYS_ACCEPT),
            app_commands.Choice(name="Request your approval first", value=DonationPolicy.REQUEST_APPROVAL),
            app_commands.Choice(name="Deny all donations", value=DonationPolicy.ALWAYS_DENY),
            app_commands.Choice(name="Accept donations from friends only", value=DonationPolicy.FRIENDS_ONLY),
        ]
    )
    async def donation(self, interaction: discord.Interaction["BallsDexBot"], policy: DonationPolicy):
        """
        Change how you want to receive donations from /balls give

        Parameters
        ----------
        policy: DonationPolicy
            The new policy for accepting donations
        """
        player, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)
        player.donation_policy = DonationPolicy(policy.value)
        if policy.value == DonationPolicy.ALWAYS_ACCEPT:
            await interaction.response.send_message(
                f"Setting updated, you will now receive all donated {settings.plural_collectible_name} immediately.",
                ephemeral=True,
            )
        elif policy.value == DonationPolicy.REQUEST_APPROVAL:
            await interaction.response.send_message(
                "Setting updated, you will now have to approve donation requests manually.", ephemeral=True
            )
        elif policy.value == DonationPolicy.ALWAYS_DENY:
            await interaction.response.send_message(
                "Setting updated, it is now impossible to use "
                f"`/{settings.players_group_cog_name} give` with "
                "you. It is still possible to perform donations using the trade system.",
                ephemeral=True,
            )
        elif policy.value == DonationPolicy.FRIENDS_ONLY:
            await interaction.response.send_message(
                "Setting updated, you will now only receive donated "
                f"{settings.plural_collectible_name} from players you have "
                "added as friends in the bot.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("Invalid input!", ephemeral=True)
            return
        await player.asave()  # do not save if the input is invalid

    @policy.command()
    @app_commands.choices(
        policy=[
            app_commands.Choice(name="Accept all mentions", value=MentionPolicy.ALLOW),
            app_commands.Choice(name="Deny all mentions", value=MentionPolicy.DENY),
        ]
    )
    async def mention(self, interaction: discord.Interaction["BallsDexBot"], policy: MentionPolicy):
        """
        Set your mention policy.

        Parameters
        ----------
        policy: MentionPolicy
            The new policy for mentions
        """
        player, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)
        player.mention_policy = policy
        await player.asave()
        await interaction.response.send_message(
            f"Your mention policy has been set to **{policy.name.lower()}**.", ephemeral=True
        )

    @policy.command()
    @app_commands.choices(
        policy=[
            app_commands.Choice(name="Accept all friend requests", value=FriendPolicy.ALLOW),
            app_commands.Choice(name="Deny all friend requests", value=FriendPolicy.DENY),
        ]
    )
    async def friends(self, interaction: discord.Interaction["BallsDexBot"], policy: FriendPolicy):
        """
        Set your friend policy.

        Parameters
        ----------
        policy: FriendPolicy
            The new policy for friend requests.
        """
        player, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)
        player.friend_policy = policy
        await player.asave()
        await interaction.response.send_message(
            f"Your friend request policy has been set to **{policy.name.lower()}**.", ephemeral=True
        )

    @policy.command()
    @app_commands.choices(
        policy=[
            app_commands.Choice(name="Use 10s acceptance cooldown", value=TradeCooldownPolicy.COOLDOWN),
            app_commands.Choice(name="Bypass acceptance cooldown", value=TradeCooldownPolicy.BYPASS),
        ]
    )
    async def trade_cooldown(self, interaction: discord.Interaction, policy: TradeCooldownPolicy):
        """
        Set your trade cooldown policy.

        Parameters
        ----------
        policy: TradeCooldownPolicy
            The new policy for trade acceptance cooldown.
        """
        player, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)
        player.trade_cooldown_policy = policy
        await player.asave()
        await interaction.response.send_message(
            f"Your trade acceptance cooldown policy has been set to **{policy.name.lower()}**.", ephemeral=True
        )

    @app_commands.command()
    async def delete(self, interaction: discord.Interaction["BallsDexBot"]):
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
        player, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)
        await player.adelete()

    @friend.command(name="add")
    async def friend_add(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User):
        """
        Add another user as a friend.

        Parameters
        ----------
        user: discord.User
            The user you want to add as a friend.
        """
        player1, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)
        player2, _ = await PlayerModel.objects.aget_or_create(discord_id=user.id)

        if player1 == player2:
            await interaction.response.send_message("You cannot add yourself as a friend.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("You cannot add a bot.", ephemeral=True)
            return
        if player2.discord_id in self.bot.blacklist:
            await interaction.response.send_message("You cannot add a blacklisted user as a friend.", ephemeral=True)
            return
        if player2.friend_policy == FriendPolicy.DENY:
            await interaction.response.send_message("This user isn't accepting friend requests.", ephemeral=True)
            return

        blocked = await player1.is_blocked(player2)
        player2_blocked = await player2.is_blocked(player1)

        if blocked:
            player_unblock = self.block_remove.extras.get("mention", "/player block remove")
            await interaction.response.send_message(
                f"You cannot add a blocked user. To unblock, use {player_unblock}.", ephemeral=True
            )
            return
        if player2_blocked:
            await interaction.response.send_message(
                "This user has blocked you, you cannot add them as a friend.", ephemeral=True
            )
            return

        friended = await player1.is_friend(player2)
        if friended:
            await interaction.response.send_message("You are already friends with this user!", ephemeral=True)
            return

        if self.active_friend_requests.get((player2.discord_id, player1.discord_id), False):
            await interaction.response.send_message(
                "That user has already sent you a friend request! "
                "Please accept or decline it before sending a new request.",
                ephemeral=True,
            )
            return

        if self.active_friend_requests.get((player1.discord_id, player2.discord_id), False):
            await interaction.response.send_message(
                "You already have an active friend request to this user!", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        view = ConfirmChoiceView(
            interaction, user=user, accept_message="Friend request accepted!", cancel_message="Friend request declined."
        )
        await interaction.followup.send(
            f"{user.mention}, {interaction.user} has sent you a friend request!",
            view=view,
            allowed_mentions=discord.AllowedMentions(users=player2.can_be_mentioned),
        )
        self.active_friend_requests[(player1.discord_id, player2.discord_id)] = True
        await view.wait()

        if not view.value:
            self.active_friend_requests[(player1.discord_id, player2.discord_id)] = False
            return

        await Friendship.objects.acreate(player1=player1, player2=player2)
        self.active_friend_requests[(player1.discord_id, player2.discord_id)] = False

    @friend.command(name="remove")
    async def friend_remove(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User):
        """
        Remove a friend.

        Parameters
        ----------
        user: discord.User
            The user you want to remove as a friend.
        """
        player1, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)
        player2, _ = await PlayerModel.objects.aget_or_create(discord_id=user.id)

        if player1 == player2:
            await interaction.response.send_message("You cannot remove yourself.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("You cannot remove a bot.", ephemeral=True)
            return

        friendship_exists = await player1.is_friend(player2)
        if not friendship_exists:
            await interaction.response.send_message("You are not friends with this user.", ephemeral=True)
            return
        else:
            await Friendship.objects.filter(
                (Q(player1=player1) & Q(player2=player2)) | (Q(player1=player2) & Q(player2=player1))
            ).adelete()
            await interaction.response.send_message(f"{user.name} has been removed as a friend.", ephemeral=True)

    @friend.command(name="list")
    async def friend_list(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        View all your friends.
        """
        player, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)

        friendships = [
            x
            async for x in Friendship.objects.filter(Q(player1=player) | Q(player2=player))
            .select_related("player1", "player2")
            .order_by("since")
            .all()
        ]

        if not friendships:
            await interaction.response.send_message("You currently do not have any friends added.", ephemeral=True)
            return

        entries: list[tuple[str, str]] = []

        for idx, relation in enumerate(friendships, start=1):
            if relation.player1 == player:
                friend = relation.player2
            else:
                friend = relation.player1

            since = format_dt(relation.since, style="f")
            entries.append(("", f"**{idx}.** <@{friend.discord_id}> ({friend.discord_id})\nSince: {since}"))

        source = FieldPageSource(entries, per_page=5, inline=False)
        source.embed.title = "Friend List"
        source.embed.set_thumbnail(url=interaction.user.display_avatar.url)
        source.embed.set_footer(text="To add a friend, use the command /player friend add.")

        pages = Menu(source=source, interaction=interaction, compact=True)
        await pages.start(ephemeral=True)

    @blocked.command(name="add")
    async def block_add(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User):
        """
        Block another user.

        Parameters
        ----------
        user: discord.User
            The user you want to block.
        """
        player1, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)
        player2, _ = await PlayerModel.objects.aget_or_create(discord_id=user.id)

        await interaction.response.defer(ephemeral=True, thinking=True)

        if player1 == player2:
            await interaction.followup.send("You cannot block yourself.", ephemeral=True)
            return
        if user.bot:
            await interaction.followup.send("You cannot block a bot.", ephemeral=True)
            return

        blocked = await player1.is_blocked(player2)
        if blocked:
            await interaction.followup.send("You have already blocked this user.", ephemeral=True)
            return
        if self.active_friend_requests.get((player1.discord_id, player2.discord_id)):
            await interaction.followup.send(
                "You cannot block a user to whom you have sent an active friend request.", ephemeral=True
            )
            return

        friended = await player1.is_friend(player2)
        if friended:
            view = ConfirmChoiceView(
                interaction,
                accept_message="User has been blocked.",
                cancel_message=f"Request cancelled, {user.name} is still your friend.",
            )
            await interaction.followup.send(
                "This user is your friend, are you sure you want to block them?", view=view, ephemeral=True
            )
            await view.wait()

            if not view.value:
                return
            else:
                await Friendship.objects.filter(
                    (Q(player1=player1) & Q(player2=player2)) | (Q(player1=player2) & Q(player2=player1))
                ).adelete()

        await Block.objects.acreate(player1=player1, player2=player2)
        await interaction.followup.send(f"You have now blocked {user.name}.", ephemeral=True)

    @blocked.command(name="remove")
    async def block_remove(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User):
        """
        Unblock a user.

        Parameters
        ----------
        user: discord.User
            The user you want to unblock.
        """
        player1, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)
        player2, _ = await PlayerModel.objects.aget_or_create(discord_id=user.id)

        if player1 == player2:
            await interaction.response.send_message("You cannot unblock yourself.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("You cannot unblock a bot.", ephemeral=True)
            return

        blocked = await player1.is_blocked(player2)

        if not blocked:
            await interaction.response.send_message("This user isn't blocked.", ephemeral=True)
            return
        else:
            await Block.objects.filter((Q(player1=player1) & Q(player2=player2))).adelete()
            await interaction.response.send_message(f"{user.name} has been unblocked.", ephemeral=True)

    @blocked.command(name="list")
    async def blocked_list(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        View all the users you have blocked.
        """
        player, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)

        blocked_relations = (
            await Block.objects.filter(player1=player).select_related("player1", "player2").order_by("date").aall()
        )

        if not blocked_relations:
            await interaction.response.send_message("You haven't blocked any users!", ephemeral=True)
            return

        entries: list[tuple[str, str]] = []

        for idx, relation in enumerate(blocked_relations, start=1):
            if relation.player1 == player:
                blocked_user = relation.player2
            else:
                blocked_user = relation.player1

            since = format_dt(relation.date, style="f")
            entries.append(
                ("", f"**{idx}.** <@{blocked_user.discord_id}> ({blocked_user.discord_id})\nBlocked at: {since}")
            )

        source = FieldPageSource(entries, per_page=5, inline=False)
        source.embed.title = "Blocked Users List"
        source.embed.set_thumbnail(url=interaction.user.display_avatar.url)
        source.embed.set_footer(text="To block a user, use the command /player block add.")

        pages = Menu(source=source, interaction=interaction, compact=True)
        await pages.start(ephemeral=True)

    @app_commands.command()
    async def info(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Display some of your info in the bot!
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            player = await PlayerModel.objects.prefetch_related("balls").aget(discord_id=interaction.user.id)
        except PlayerModel.DoesNotExist:
            await interaction.followup.send("You haven't got any info to show!", ephemeral=True)
            return
        ball = await BallInstance.objects.prefetch_related("special", "trade_player").filter(player=player).aall()

        user = interaction.user
        bot_countryballs = {x: y.emoji_id for x, y in balls.items() if y.enabled}
        total_countryballs = len(bot_countryballs)
        owned_countryballs = set(
            [x[0] async for x in player.balls.filter(ball__enabled=True).distinct().values_list("ball_id")]
        )

        if total_countryballs > 0:
            completion_percentage = f"{round(len(owned_countryballs) / total_countryballs * 100, 1)}%"
        else:
            completion_percentage = "0.0%"

        caught_owned = [x for x in ball if x.trade_player is None]
        balls_owned = [x for x in ball]
        special = [x for x in ball if x.special is not None]
        trades = Trade.objects.filter(
            Q(player1__discord_id=interaction.user.id) | Q(player2__discord_id=interaction.user.id)
        ).values_list("player1__discord_id", "player2__discord_id")

        trade_partners = set()
        async for p1, p2 in trades:
            if p1 != interaction.user.id:
                trade_partners.add(p1)
            if p2 != interaction.user.id:
                trade_partners.add(p2)

        friends = await Friendship.objects.filter(
            Q(player1__discord_id=interaction.user.id) | Q(player2__discord_id=interaction.user.id)
        ).acount()
        blocks = await Block.objects.filter(player1__discord_id=interaction.user.id).acount()

        embed = discord.Embed(
            title=f"**{user.display_name.title()}'s {settings.bot_name.title()} Info**", color=discord.Color.blurple()
        )
        embed.description = (
            "Here are your statistics and settings in the bot!\n"
            "## Player Info\n"
            f"**Privacy Policy:** {PRIVATE_POLICY_MAP[player.privacy_policy]}\n"
            f"**Donation Policy:** {DONATION_POLICY_MAP[player.donation_policy]}\n"
            f"**Mention Policy:** {MENTION_POLICY_MAP[player.mention_policy]}\n"
            f"**Friend Policy:** {FRIEND_POLICY_MAP[player.friend_policy]}\n"
            f"**Trade Cooldown Policy:** {TRADE_POLICY_MAP[player.trade_cooldown_policy]}\n"
            f"**Amount of Friends:** {friends}\n"
            f"**Amount of Blocked Users:** {blocks}\n"
            "## Player Stats\n"
            f"**Completion:** {completion_percentage}\n"
            f"**{settings.collectible_name.title()}s Owned:** {len(balls_owned):,}\n"
            f"**Caught {settings.collectible_name.title()}s Owned**: {len(caught_owned):,}\n"
            f"**Special {settings.collectible_name.title()}s:** {len(special):,}\n"
            f"**Trades Completed:** {len(trades):,}\n"
            f"**Amount of Users Traded With:** {len(trade_partners):,}\n"
            f"**Current Balance:** {player.money:,}"
        )
        embed.set_footer(text="Keep collecting and trading to improve your stats!")
        embed.set_thumbnail(url=user.display_avatar)  # type: ignore
        await interaction.followup.send(embed=embed, ephemeral=True)

    @money.command()
    async def balance(self, interaction: discord.Interaction):
        """
        Check your balance.
        """
        player, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)
        await interaction.response.send_message(f"Your balance is **{player.money:,}**.", ephemeral=True)

    @money.command()
    async def give(self, interaction: discord.Interaction, user: discord.User, amount: int):
        """
        Give coins to another user.

        Parameters
        ----------
        user: discord.User
            The user you want to give coins to.
        amount: int
            The amount of coins to give.
        """
        player, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)
        if not player.can_afford(amount):
            await interaction.response.send_message("You do not have enough coins to give.", ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message("The amount must be greater than zero.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("You cannot give coins to a bot.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message("You cannot give coins to yourself.", ephemeral=True)
            return
        other_player, _ = await PlayerModel.objects.aget_or_create(discord_id=user.id)
        await player.remove_money(amount)
        await other_player.add_money(amount)
        await interaction.response.send_message(f"{amount:,} coins have been given to {user.mention}.", ephemeral=True)

    @app_commands.command()
    @app_commands.choices(
        type=[
            app_commands.Choice(name=settings.collectible_name.title(), value="balls"),
            app_commands.Choice(name="Trades", value="trades"),
            app_commands.Choice(name="All", value="all"),
        ]
    )
    async def export(self, interaction: discord.Interaction["BallsDexBot"], type: str):
        """
        Export your player data.
        """
        player = await PlayerModel.objects.aget_or_none(discord_id=interaction.user.id)
        if player is None:
            await interaction.response.send_message("You don't have any player data to export.", ephemeral=True)
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
                "Your data is too large to export.Please contact the bot support for more information.", ephemeral=True
            )
            return
        files = [discord.File(zip_file, "player_data.zip")]
        try:
            await interaction.user.send("Here is your player data:", files=files)
            await interaction.followup.send("Your player data has been sent via DMs.", ephemeral=True)
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
    balls = BallInstance.objects.prefetch_related("ball", "trade_player", "special").filter(player=player)
    txt = f"id,hex id,{settings.collectible_name},catch date,trade_player,special,attack,attack bonus,hp,hp_bonus\n"
    async for ball in balls:
        txt += (
            f"{ball.pk},{ball.pk:0X},{ball.countryball.country},{ball.catch_date},"
            f"{ball.trade_player.discord_id if ball.trade_player else 'None'},{ball.special},"
            f"{ball.attack},{ball.attack_bonus},{ball.health},{ball.health_bonus}\n"
        )
    return BytesIO(txt.encode("utf-8"))


async def get_trades_csv(player: PlayerModel) -> BytesIO:
    """
    Get a CSV file with all trades of the player.
    """
    trade_history = (
        Trade.objects.filter(Q(player1=player) | Q(player2=player))
        .order_by("date")
        .prefetch_related("player1", "player2")
    )
    txt = "id,date,player1,player2,player1 received,player2 received\n"
    async for trade in trade_history:
        player1_items = TradeObject.objects.prefetch_related("ballinstance").filter(trade=trade, player=trade.player1)
        player2_items = TradeObject.objects.prefetch_related("ballinstance").filter(trade=trade, player=trade.player2)
        txt += (
            f"{trade.pk},{trade.date},{trade.player1.discord_id},{trade.player2.discord_id},"
            f"{','.join([str(i.ballinstance) async for i in player2_items])},"
            f"{','.join([str(i.ballinstance) async for i in player1_items])}\n"
        )
    return BytesIO(txt.encode("utf-8"))
