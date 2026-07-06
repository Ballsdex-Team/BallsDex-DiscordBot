import datetime
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from discord.utils import format_dt
from django.urls import reverse
from django.utils.timezone import get_current_timezone

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.discord import LayoutView
from ballsdex.core.translation import current_locale, t
from ballsdex.core.utils import checks
from ballsdex.core.utils.enums import DONATION_POLICY_MAP, FRIEND_POLICY_MAP, MENTION_POLICY_MAP, PRIVATE_POLICY_MAP
from ballsdex.core.utils.menus import Menu, TextFormatter, TextSource
from bd_models.models import BallInstance, GuildConfig, Player
from settings.models import settings

if TYPE_CHECKING:
    from django.db.models import QuerySet


class PlayerInfoView(discord.ui.View):
    def __init__(self, player: Player, username: str):
        super().__init__()
        self.player = player
        self.username = username
        # @discord.ui.button() label is resolved once at class-body (import) time - override it
        # here so t() sees the locale of whoever ran the command that creates this view
        self.recently_caught.label = t("Recent Catches")

    @discord.ui.button(label="Recent Catches", style=discord.ButtonStyle.primary)
    async def recently_caught(self, interaction: discord.Interaction, button: discord.ui.Button):
        # this view does not extend ballsdex.core.discord.View, so the locale isn't set
        # automatically - set it here, at the top of the only entry point into this view
        current_locale.set(interaction.locale.value)
        # Display the last 10 catches of the user, and how long it took for each catch
        recent_balls = (
            await BallInstance.objects.filter(player=self.player, spawned_time__isnull=False, trade_player=None)
            .select_related("ball")
            .order_by("-catch_date")[:10]
            .aall()
        )
        embed = discord.Embed(
            title=t("Last {count} catches for {user}").format(count=len(recent_balls), user=self.username)
        )
        for ball in recent_balls:
            catch_time = (ball.catch_date - ball.spawned_time).total_seconds()  # type: ignore
            embed.add_field(
                name=ball.description(short=True),
                value=t("{time:.3f}s in {server}").format(time=catch_time, server=ball.server_id),
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class GuildInfoView(discord.ui.View):
    def __init__(self, queryset: "QuerySet[BallInstance]", days: int):
        super().__init__()
        self.queryset = queryset
        self.days = days
        # @discord.ui.button() label is resolved once at class-body (import) time - override it
        # here so t() sees the locale of whoever ran the command that creates this view
        self.list_catchers.label = t("List catchers")

    @discord.ui.button(label="List catchers", style=discord.ButtonStyle.primary)
    async def list_catchers(self, interaction: discord.Interaction[BallsDexBot], button: discord.ui.Button):
        # this view does not extend ballsdex.core.discord.View, so the locale isn't set
        # automatically - set it here, at the top of the only entry point into this view
        current_locale.set(interaction.locale.value)
        await interaction.response.defer(thinking=True, ephemeral=True)
        counts: dict[int, int] = {}
        async for instance in self.queryset:
            counts[instance.player.discord_id] = counts.get(instance.player.discord_id, 0) + 1
        if not counts:
            await interaction.followup.send(t("No catches found for this period."), ephemeral=True)
            return

        lines: list[str] = []
        for discord_id, count in sorted(counts.items(), key=lambda item: item[1], reverse=True):
            user = interaction.client.get_user(discord_id)
            if not user:
                try:
                    user = await interaction.client.fetch_user(discord_id)
                except discord.NotFound:
                    user = None
            name = (user.global_name or user.name) if user else t("Unknown user")
            mention = user.mention if user else f"<@{discord_id}>"
            lines.append(f"{mention} - {name} ({discord_id}) - {count}")

        view = LayoutView()
        text_item = discord.ui.TextDisplay("")
        view.add_item(text_item)
        menu = Menu(interaction.client, view, TextSource("\n".join(lines)), TextFormatter(text_item))
        await menu.init()
        await interaction.followup.send(view=view, ephemeral=True)


@commands.hybrid_group()
@checks.has_permissions("bd_models.view_guildconfig", "bd_models.view_player")
async def info(ctx: commands.Context[BallsDexBot]):
    """
    Information commands
    """
    await ctx.send_help(ctx.command)


_DAYS_PRESETS = (7, 14, 30, 90)


async def _days_autocomplete(
    interaction: discord.Interaction[BallsDexBot], current: str
) -> list[discord.app_commands.Choice[int]]:
    choices = [
        discord.app_commands.Choice(name=t("{days} days").format(days=preset), value=preset) for preset in _DAYS_PRESETS
    ]
    if current.strip().isdigit():
        custom = int(current.strip())
        if custom not in _DAYS_PRESETS:
            choices.insert(0, discord.app_commands.Choice(name=t("{days} days").format(days=custom), value=custom))
    return choices[:25]


@info.command()
@checks.has_permissions("bd_models.view_guildconfig")
async def guild(ctx: commands.Context[BallsDexBot], guild_id: str, days: int = 7):
    """
    Show information about the server provided

    Parameters
    ----------
    guild: discord.Guild | None
        The guild you want to get information about.
    guild_id: str | None
        The ID of the guild you want to get information about.
    days: int
        The amount of days to look back for the amount of countryballs caught.
    """
    await ctx.defer(ephemeral=True)
    guild = ctx.bot.get_guild(int(guild_id))

    if not guild:
        try:
            guild = await ctx.bot.fetch_guild(int(guild_id))  # type: ignore
        except ValueError:
            await ctx.send(t("The guild ID you gave is not valid."), ephemeral=True)
            return
        except discord.NotFound:
            await ctx.send(t("The given guild ID could not be found."), ephemeral=True)
            return

    url = None
    if config := await GuildConfig.objects.aget_or_none(guild_id=guild.id):
        spawn_enabled = config.enabled and config.guild_id
        url = f"{settings.site_base_url}{reverse('admin:bd_models_guildconfig_change', args=(config.pk,))}"
    else:
        spawn_enabled = False

    total_server_balls = BallInstance.objects.filter(
        catch_date__gte=datetime.datetime.now(tz=get_current_timezone()) - datetime.timedelta(days=days),
        server_id=guild.id,
    ).prefetch_related("player")
    if guild.owner_id:
        owner = await ctx.bot.fetch_user(guild.owner_id)
        embed = discord.Embed(
            title=f"{guild.name} ({guild.id})",
            url=url,
            description=t("**Owner:** {owner} ({owner_id})").format(owner=owner, owner_id=guild.owner_id),
            color=discord.Color.blurple(),
        )
    else:
        embed = discord.Embed(title=f"{guild.name} ({guild.id})", url=url, color=discord.Color.blurple())
    embed.add_field(name=t("Members:"), value=guild.member_count)
    embed.add_field(name=t("Spawn enabled:"), value=spawn_enabled)
    embed.add_field(name=t("Created at:"), value=format_dt(guild.created_at, style="F"))
    embed.add_field(
        name=t("{collectibles} caught ({days} days):").format(
            collectibles=settings.plural_collectible_name.title(), days=days
        ),
        value=await total_server_balls.acount(),
    )
    embed.add_field(
        name=t("Amount of users who caught\n{collectibles} ({days} days):").format(
            collectibles=settings.plural_collectible_name, days=days
        ),
        value=len(set([x.player.discord_id async for x in total_server_balls])),
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await ctx.send(embed=embed, ephemeral=True, view=GuildInfoView(total_server_balls, days))


@info.command()
@checks.has_permissions("bd_models.view_player", "bd_models.view_ballinstance")
async def user(ctx: commands.Context[BallsDexBot], user: discord.User, days: int = 7):
    """
    Show information about the user provided

    Parameters
    ----------
    user: discord.User | None
        The user you want to get information about.
    days: int
        The amount of days to look back for the amount of countryballs caught.
    """
    await ctx.defer(ephemeral=True)
    player = await Player.objects.aget_or_none(discord_id=user.id)
    if not player:
        await ctx.send(t("The user you gave does not exist."), ephemeral=True)
        return
    url = f"{settings.site_base_url}{reverse('admin:bd_models_player_change', args=(player.pk,))}"
    total_user_balls = await BallInstance.objects.filter(
        catch_date__gte=datetime.datetime.now(tz=get_current_timezone()) - datetime.timedelta(days=days), player=player
    ).aall()
    embed = discord.Embed(
        title=f"{user} ({user.id})",
        url=url,
        description=t(
            "**Privacy Policy:** {privacy}\n**Donation Policy:** {donation}\n"
            "**Mention Policy:** {mention}\n**Friend Policy:** {friend}"
        ).format(
            privacy=t(PRIVATE_POLICY_MAP[player.privacy_policy]),
            donation=t(DONATION_POLICY_MAP[player.donation_policy]),
            mention=t(MENTION_POLICY_MAP[player.mention_policy]),
            friend=t(FRIEND_POLICY_MAP[player.friend_policy]),
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name=t("{collectibles} caught ({days} days):").format(
            collectibles=settings.plural_collectible_name.title(), days=days
        ),
        value=len(total_user_balls),
    )
    embed.add_field(
        name=t("Unique {collectibles} caught ({days} days):").format(
            collectibles=settings.plural_collectible_name, days=days
        ),
        value=len(set([ball.countryball for ball in total_user_balls])),
    )
    embed.add_field(
        name=t("Total servers with {collectibles} caught ({days} days):").format(
            collectibles=settings.plural_collectible_name, days=days
        ),
        value=len(set([x.server_id for x in total_user_balls])),
    )
    embed.add_field(
        name=t("Total {collectibles} caught:").format(collectibles=settings.plural_collectible_name),
        value=await BallInstance.objects.filter(player__discord_id=user.id).acount(),
    )
    embed.add_field(
        name=t("Total unique {collectibles} caught:").format(collectibles=settings.plural_collectible_name),
        value=len(set([x.countryball for x in total_user_balls])),
    )
    embed.add_field(
        name=t("Total servers with {collectibles} caught:").format(collectibles=settings.plural_collectible_name),
        value=len(set([x.server_id for x in total_user_balls])),
    )
    embed.set_thumbnail(url=user.display_avatar)  # type: ignore
    await ctx.send(embed=embed, ephemeral=True, view=PlayerInfoView(player, user.name))


guild.autocomplete("days")(_days_autocomplete)
user.autocomplete("days")(_days_autocomplete)
