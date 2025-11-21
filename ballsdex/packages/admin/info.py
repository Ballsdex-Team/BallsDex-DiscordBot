import datetime

import discord
from discord.ext import commands
from discord.utils import format_dt
from django.urls import reverse
from django.utils.timezone import get_current_timezone

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.utils.enums import DONATION_POLICY_MAP, FRIEND_POLICY_MAP, MENTION_POLICY_MAP, PRIVATE_POLICY_MAP
from bd_models.models import BallInstance, GuildConfig, Player
from settings.models import settings


@commands.hybrid_group()
async def info(ctx: commands.Context[BallsDexBot]):
    """
    Information commands
    """
    await ctx.send_help(ctx.command)


@info.command()
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
            await ctx.send("The guild ID you gave is not valid.", ephemeral=True)
            return
        except discord.NotFound:
            await ctx.send("The given guild ID could not be found.", ephemeral=True)
            return

    url = None
    if config := await GuildConfig.objects.aget_or_none(guild_id=guild.id):
        spawn_enabled = config.enabled and config.guild_id
        url = reverse("admin:bd_models_guildconfig_change", args=(config.pk,))
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
            description=f"**Owner:** {owner} ({guild.owner_id})",
            color=discord.Color.blurple(),
        )
    else:
        embed = discord.Embed(title=f"{guild.name} ({guild.id})", url=url, color=discord.Color.blurple())
    embed.add_field(name="Members:", value=guild.member_count)
    embed.add_field(name="Spawn enabled:", value=spawn_enabled)
    embed.add_field(name="Created at:", value=format_dt(guild.created_at, style="F"))
    embed.add_field(
        name=f"{settings.plural_collectible_name.title()} caught ({days} days):",
        value=await total_server_balls.acount(),
    )
    embed.add_field(
        name=f"Amount of users who caught\n{settings.plural_collectible_name} ({days} days):",
        value=len(set([x.player.discord_id async for x in total_server_balls])),
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await ctx.send(embed=embed, ephemeral=True)


@info.command()
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
        await ctx.send("The user you gave does not exist.", ephemeral=True)
        return
    url = reverse("admin:bd_models_player_change", args=(player.pk,))
    total_user_balls = await BallInstance.objects.filter(
        catch_date__gte=datetime.datetime.now(tz=get_current_timezone()) - datetime.timedelta(days=days), player=player
    ).aall()
    embed = discord.Embed(
        title=f"{user} ({user.id})",
        url=url,
        description=(
            f"**Privacy Policy:** {PRIVATE_POLICY_MAP[player.privacy_policy]}\n"
            f"**Donation Policy:** {DONATION_POLICY_MAP[player.donation_policy]}\n"
            f"**Mention Policy:** {MENTION_POLICY_MAP[player.mention_policy]}\n"
            f"**Friend Policy:** {FRIEND_POLICY_MAP[player.friend_policy]}"
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name=f"{settings.plural_collectible_name.title()} caught ({days} days):", value=len(total_user_balls)
    )
    embed.add_field(
        name=f"Unique {settings.plural_collectible_name} caught ({days} days):",
        value=len(set([ball.countryball for ball in total_user_balls])),
    )
    embed.add_field(
        name=f"Total servers with {settings.plural_collectible_name} caught ({days} days):",
        value=len(set([x.server_id for x in total_user_balls])),
    )
    embed.add_field(
        name=f"Total {settings.plural_collectible_name} caught:",
        value=await BallInstance.objects.filter(player__discord_id=user.id).acount(),
    )
    embed.add_field(
        name=f"Total unique {settings.plural_collectible_name} caught:",
        value=len(set([x.countryball for x in total_user_balls])),
    )
    embed.add_field(
        name=f"Total servers with {settings.plural_collectible_name} caught:",
        value=len(set([x.server_id for x in total_user_balls])),
    )
    embed.set_thumbnail(url=user.display_avatar)  # type: ignore
    await ctx.send(embed=embed, ephemeral=True)
