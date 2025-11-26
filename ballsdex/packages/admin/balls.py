import asyncio
import logging
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands
from discord.utils import format_dt
from django.urls import reverse

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.utils import checks
from ballsdex.core.utils.buttons import ConfirmChoiceView
from bd_models.models import Ball, BallInstance, Player, Special, Trade, TradeObject
from settings.models import settings

from .flags import BallsCountFlags, GiveBallFlags, SpawnFlags

if TYPE_CHECKING:
    from ballsdex.packages.countryballs.cog import CountryBallsSpawner
    from ballsdex.packages.countryballs.countryball import BallSpawnView

log = logging.getLogger("ballsdex.packages.admin.balls")
FILENAME_RE = re.compile(r"^(.+)(\.\S+)$")


async def save_file(attachment: discord.Attachment) -> Path:
    path = Path(f"./admin_panel/media/{attachment.filename}")
    match = FILENAME_RE.match(attachment.filename)
    if not match:
        raise TypeError("The file you uploaded lacks an extension.")
    i = 1
    while path.exists():
        path = Path(f"./admin_panel/media/{match.group(1)}-{i}{match.group(2)}")
        i = i + 1
    await attachment.save(path)
    return path.relative_to("./admin_panel/media/")


async def _spawn_bomb(
    ctx: commands.Context[BallsDexBot],
    countryball_cls: type["BallSpawnView"],
    countryball: Ball | None,
    channel: discord.TextChannel,
    n: int,
    special: Special | None = None,
    atk_bonus: int | None = None,
    hp_bonus: int | None = None,
):
    spawned = 0
    message: discord.Message

    async def update_message_loop():
        nonlocal spawned, message
        for i in range(5 * 12 * 10):  # timeout progress after 10 minutes
            await edit_func(
                content=f"Spawn bomb in progress in {channel.mention}, "
                f"{settings.collectible_name.title()}: {countryball or 'Random'}\n"
                f"{spawned}/{n} spawned ({round((spawned / n) * 100)}%)"
            )
            await asyncio.sleep(5)
        await edit_func(content="Spawn bomb seems to have timed out.")

    message = await ctx.send(f"Starting spawn bomb in {channel.mention}...", ephemeral=True)
    edit_func = ctx.interaction.edit_original_response if ctx.interaction else message.edit
    task = ctx.bot.loop.create_task(update_message_loop())
    try:
        for i in range(n):
            if not countryball:
                ball = await countryball_cls.get_random(ctx.bot)
            else:
                ball = countryball_cls(ctx.bot, countryball)
            ball.special = special
            ball.atk_bonus = atk_bonus
            ball.hp_bonus = hp_bonus
            result = await ball.spawn(channel)
            if not result:
                task.cancel()
                await edit_func(
                    content=f"A {settings.collectible_name} failed to spawn, probably "
                    "indicating a lack of permissions to send messages "
                    f"or upload files in {channel.mention}."
                )
                return
            spawned += 1
        task.cancel()
        await edit_func(
            content=f"Successfully spawned {spawned} {settings.plural_collectible_name} in {channel.mention}!"
        )
    finally:
        task.cancel()


@commands.hybrid_group(name=settings.balls_slash_name)
async def balls(ctx: commands.Context[BallsDexBot]):
    """
    Countryballs management
    """
    await ctx.send_help(ctx.command)


@balls.command()
@checks.has_permissions("bd_models.add_ballinstance")
async def spawn(ctx: commands.Context[BallsDexBot], *, flags: SpawnFlags):
    """
    Force spawn a random or specified countryball.
    """
    # the transformer triggered a response, meaning user tried an incorrect input
    cog = cast("CountryBallsSpawner | None", ctx.bot.get_cog("CountryBallsSpawner"))
    if not cog:
        prefix = settings.prefix if ctx.bot.intents.message_content or not ctx.bot.user else f"{ctx.bot.user.mention} "
        # do not replace `countryballs` with `settings.collectible_name`, it is intended
        await ctx.send(
            "The `countryballs` package is not loaded, this command is unavailable.\n"
            "Please resolve the errors preventing this package from loading. Use "
            f'"{prefix}reload countryballs" to try reloading it.',
            ephemeral=True,
        )
        return

    special_attrs = []
    if flags.special is not None:
        special_attrs.append(f"special={flags.special.name}")
    if flags.atk_bonus is not None:
        special_attrs.append(f"atk={flags.atk_bonus}")
    if flags.hp_bonus is not None:
        special_attrs.append(f"hp={flags.hp_bonus}")
    if flags.n > 1:
        await _spawn_bomb(
            ctx,
            cog.countryball_cls,
            flags.countryball,
            flags.channel or ctx.channel,  # type: ignore
            flags.n,
            flags.special,
            flags.atk_bonus,
            flags.hp_bonus,
        )
        log.info(
            f"{ctx.author} spawned {settings.collectible_name}"
            f" {flags.countryball or 'random'} {flags.n} times in {flags.channel or ctx.channel}"
            + (f" ({', '.join(special_attrs)})." if special_attrs else "."),
            extra={"webhook": True},
        )
        return

    await ctx.defer(ephemeral=True)
    if not flags.countryball:
        ball = await cog.countryball_cls.get_random(ctx.bot)
    else:
        ball = cog.countryball_cls(ctx.bot, flags.countryball)
    ball.special = flags.special
    ball.atk_bonus = flags.atk_bonus
    ball.hp_bonus = flags.hp_bonus
    result = await ball.spawn(flags.channel or ctx.channel)  # type: ignore

    if result:
        await ctx.send(f"{settings.collectible_name.title()} spawned.", ephemeral=True)
        log.info(
            f"{ctx.author} spawned {settings.collectible_name} {ball.name} "
            f"in {flags.channel or ctx.channel}" + (f" ({', '.join(special_attrs)})." if special_attrs else "."),
            extra={"webhook": True},
        )


@balls.command()
@checks.has_permissions("bd_models.add_ballinstance")
async def give(ctx: commands.Context[BallsDexBot], user: discord.User, *, flags: GiveBallFlags):
    """
    Give the specified countryball to a player.

    Parameters
    ----------
    user: discord.User
        The user you want to give a countryball to
    """
    await ctx.defer(ephemeral=True)

    player, created = await Player.objects.aget_or_create(discord_id=user.id)
    instance = await BallInstance.objects.acreate(
        ball=flags.countryball,
        player=player,
        attack_bonus=(
            flags.attack_bonus
            if flags.attack_bonus is not None
            else random.randint(-settings.max_attack_bonus, settings.max_attack_bonus)
        ),
        health_bonus=(
            flags.health_bonus
            if flags.health_bonus is not None
            else random.randint(-settings.max_health_bonus, settings.max_health_bonus)
        ),
        special=flags.special,
    )
    await ctx.send(
        f"`{flags.countryball.country}` {settings.collectible_name} was successfully given to "
        f"`{user}`.\nSpecial: `{flags.special.name if flags.special else None}` • ATK: "
        f"`{instance.attack_bonus:+d}` • HP:`{instance.health_bonus:+d}` "
    )
    log.info(
        f"{ctx.author} gave {settings.collectible_name} "
        f"{flags.countryball.country} to {user}. (Special={flags.special.name if flags.special else None} "
        f"ATK={instance.attack_bonus:+d} HP={instance.health_bonus:+d}).",
        extra={"webhook": True},
    )


@balls.command(name="info")
@checks.has_permissions("bd_models.view_ballinstance")
async def balls_info(ctx: commands.Context[BallsDexBot], countryball_id: str):
    """
    Show information about a countryball.

    Parameters
    ----------
    countryball_id: str
        The ID of the countryball you want to get information about.
    """
    try:
        pk = int(countryball_id, 16)
    except ValueError:
        await ctx.send(f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True)
        return
    try:
        ball = await BallInstance.objects.prefetch_related("player", "trade_player", "special").aget(id=pk)
    except BallInstance.DoesNotExist:
        await ctx.send(f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True)
        return
    spawned_time = format_dt(ball.spawned_time, style="R") if ball.spawned_time else "N/A"
    catch_time = (
        (ball.catch_date - ball.spawned_time).total_seconds() if ball.catch_date and ball.spawned_time else "N/A"
    )
    admin_url = f"[View online](<{reverse('admin:bd_models_ballinstance_change', args=(ball.pk,))}>)"
    await ctx.send(
        f"**{settings.collectible_name.title()} ID:** {ball.pk}\n"
        f"**Player:** {ball.player}\n"
        f"**Name:** {ball.countryball}\n"
        f"**Attack:** {ball.attack}\n"
        f"**Attack bonus:** {ball.attack_bonus}\n"
        f"**Health bonus:** {ball.health_bonus}\n"
        f"**Health:** {ball.health}\n"
        f"**Special:** {ball.special.name if ball.special else None}\n"
        f"**Caught at:** {format_dt(ball.catch_date, style='R')}\n"
        f"**Spawned at:** {spawned_time}\n"
        f"**Catch time:** {catch_time} seconds\n"
        f"**Caught in:** {ball.server_id if ball.server_id else 'N/A'}\n"
        f"**Traded:** {ball.trade_player}\n{admin_url}",
        ephemeral=True,
    )
    log.info(f"{ctx.author} got info for {ball}({ball.pk}).", extra={"webhook": True})


@balls.command(name="delete")
@checks.has_permissions("bd_models.delete_ballinstance")
async def balls_delete(ctx: commands.Context[BallsDexBot], countryball_id: str, soft_delete: bool = True):
    """
    Delete a countryball.

    Parameters
    ----------
    countryball_id: str
        The ID of the countryball you want to delete.
    soft_delete: bool
        Whether the countryball should be kept in database or fully wiped.
    """
    try:
        ballIdConverted = int(countryball_id, 16)
    except ValueError:
        await ctx.send(f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True)
        return
    try:
        ball = await BallInstance.objects.aget(id=ballIdConverted)
    except BallInstance.DoesNotExist:
        await ctx.send(f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True)
        return
    if soft_delete:
        ball.deleted = True
        await ball.asave()
        await ctx.send(f"{settings.collectible_name.title()} {countryball_id} soft deleted.", ephemeral=True)
        log.info(f"{ctx.author} soft deleted {ball}({ball.pk}).", extra={"webhook": True})
    else:
        await ball.adelete()
        await ctx.send(f"{settings.collectible_name.title()} {countryball_id} hard deleted.", ephemeral=True)
        log.info(f"{ctx.author} hard deleted {ball}({ball.pk}).", extra={"webhook": True})


@balls.command(name="transfer")
@checks.has_permissions("bd_models.change_ballinstance")
async def balls_transfer(ctx: commands.Context[BallsDexBot], countryball_id: str, user: discord.User):
    """
    Transfer a countryball to another user.

    Parameters
    ----------
    countryball_id: str
        The ID of the countryball you want to transfer.
    user: discord.User
        The user you want to transfer the countryball to.
    """
    try:
        ballIdConverted = int(countryball_id, 16)
    except ValueError:
        await ctx.send(f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True)
        return
    try:
        ball = await BallInstance.objects.prefetch_related("player").aget(id=ballIdConverted)
        original_player = ball.player
    except BallInstance.DoesNotExist:
        await ctx.send(f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True)
        return
    player, _ = await Player.objects.aget_or_create(discord_id=user.id)
    ball.player = player
    await ball.asave()

    trade = await Trade.objects.acreate(player1=original_player, player2=player)
    await TradeObject.objects.acreate(trade=trade, ballinstance=ball, player=original_player)
    await ctx.send(f"Transfered {ball}({ball.pk}) from {original_player} to {user}.", ephemeral=True)
    log.info(f"{ctx.author} transferred {ball}({ball.pk}) from {original_player} to {user}.", extra={"webhook": True})


@balls.command(name="reset")
@checks.has_permissions("bd_models.delete_ballinstance", "bd_models.change_ballinstance")
async def balls_reset(
    ctx: commands.Context[BallsDexBot], user: discord.User, percentage: int | None = None, soft_delete: bool = True
):
    """
    Reset a player's countryballs.

    Parameters
    ----------
    user: discord.User
        The user you want to reset the countryballs of.
    percentage: int | None
        The percentage of countryballs to delete, if not all. Used for sanctions.
    soft_delete: bool
        If true, the countryballs will be marked as deleted instead of being removed from the
        database.
    """
    player = await Player.objects.aget_or_none(discord_id=user.id)
    if not player:
        await ctx.send("The user you gave does not exist.", ephemeral=True)
        return
    if percentage and not 0 < percentage < 100:
        await ctx.send("The percentage must be between 1 and 99.", ephemeral=True)
        return
    await ctx.defer(ephemeral=True)

    method = "soft" if soft_delete else "hard"
    if not percentage:
        text = f"Are you sure you want to {method} delete {user}'s {settings.plural_collectible_name}?"
    else:
        text = f"Are you sure you want to {method} delete {percentage}% of {user}'s {settings.plural_collectible_name}?"
    view = ConfirmChoiceView(
        ctx,
        accept_message=f"Confirmed, {method} deleting the {settings.plural_collectible_name}...",
        cancel_message="Request cancelled.",
    )
    await ctx.send(text, view=view, ephemeral=True)
    await view.wait()
    if not view.value:
        return
    if percentage:
        balls = [x async for x in BallInstance.objects.filter(player=player)]
        to_delete = random.sample(balls, int(len(balls) * (percentage / 100)))
        for ball in to_delete:
            if soft_delete:
                ball.deleted = True
                await ball.asave()
            else:
                await ball.adelete()
        count = len(to_delete)
    else:
        if soft_delete:
            count = await BallInstance.all_objects.filter(player=player).aupdate(deleted=True)
        else:
            count = await BallInstance.all_objects.filter(player=player).adelete()
    await ctx.send(f"{count} {settings.plural_collectible_name} from {user} have been deleted.", ephemeral=True)
    log.info(
        f"{ctx.author} deleted {percentage or 100}% of {player}'s {settings.plural_collectible_name}.",
        extra={"webhook": True},
    )


@balls.command(name="count")
@checks.has_permissions("bd_models.view_ballinstance")
async def balls_count(ctx: commands.Context[BallsDexBot], *, flags: BallsCountFlags):
    """
    Count the number of countryballs that a player has or how many exist in total.
    """
    filters = {}
    if flags.countryball:
        filters["ball"] = flags.countryball
    if flags.special:
        filters["special"] = flags.special
    if flags.user:
        filters["player__discord_id"] = flags.user.id
    await ctx.defer(ephemeral=True)
    qs = BallInstance.all_objects if flags.deleted else BallInstance.objects
    balls = await qs.filter(**filters).acount()
    verb = "is" if balls == 1 else "are"
    country = f"{flags.countryball.country} " if flags.countryball else ""
    plural = "s" if balls > 1 or balls == 0 else ""
    special_str = f"{flags.special.name} " if flags.special else ""
    if flags.user:
        await ctx.send(
            f"{flags.user} has {balls} {special_str}{country}{settings.collectible_name}{plural}.", ephemeral=True
        )
    else:
        await ctx.send(
            f"There {verb} {balls} {special_str}{country}{settings.collectible_name}{plural}.", ephemeral=True
        )
