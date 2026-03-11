from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from django.db.models import Q

from ballsdex.core.discord import LayoutView
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.enums import DONATION_POLICY_MAP, FRIEND_POLICY_MAP, MENTION_POLICY_MAP, PRIVATE_POLICY_MAP
from ballsdex.core.utils.enums import TRADE_COOLDOWN_POLICY_MAP as TRADE_POLICY_MAP
from ballsdex.core.utils.menus import ItemFormatter, ListSource, Menu, dynamic_chunks
from bd_models.enums import FriendPolicy
from bd_models.models import BallInstance, Block, Friendship, Trade, balls
from bd_models.models import Player as PlayerModel
from settings.models import settings

from .views import RelationContainer, SettingsContainer

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
    # money = app_commands.Group(name="money", description="Money commands")

    @app_commands.command(name="settings")
    async def psettings(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Edit your player settings
        """
        player, _ = await PlayerModel.objects.aget_or_create(discord_id=interaction.user.id)
        layout = LayoutView()
        container = SettingsContainer()
        container.configure(interaction, player)
        layout.add_item(container)
        await interaction.response.send_message(view=layout, ephemeral=True)

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
        qs = (
            Friendship.objects.filter(Q(player1=player) | Q(player2=player))
            .select_related("player1", "player2")
            .order_by("since")
        )

        if not await qs.aexists():
            await interaction.response.send_message("You currently do not have any friends added.", ephemeral=True)
            return

        view = LayoutView()
        container = RelationContainer()
        container.title.content = "# Your friend list\nAdd friends with {cmd}".format(
            cmd=self.friend_add.extras.get("mention", "`/player friend add`")
        )
        view.add_item(container)
        menu = Menu(
            self.bot,
            view,
            ListSource(await dynamic_chunks(view, container.paginate_relations(qs, player))),
            ItemFormatter(container, 1),
        )
        await menu.init()
        await interaction.response.send_message(view=view, ephemeral=True)

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
        qs = Block.objects.filter(player1=player).select_related("player1", "player2").order_by("date")

        if not await qs.aexists():
            await interaction.response.send_message("You haven't blocked any users!", ephemeral=True)
            return

        view = LayoutView()
        container = RelationContainer()
        container.title.content = "# Your block list\nBlock users with {cmd}".format(
            cmd=self.block_add.extras.get("mention", "`/player block add`")
        )
        view.add_item(container)
        menu = Menu(
            self.bot,
            view,
            ListSource(await dynamic_chunks(view, container.paginate_relations(qs, player))),
            ItemFormatter(container, 1),
        )
        await menu.init()
        await interaction.response.send_message(view=view, ephemeral=True)

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
            # f"**Current Balance:** {player.money:,}"
        )
        embed.set_footer(text="Keep collecting and trading to improve your stats!")
        embed.set_thumbnail(url=user.display_avatar)  # type: ignore
        await interaction.followup.send(embed=embed, ephemeral=True)
