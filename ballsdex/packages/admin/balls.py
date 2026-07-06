import asyncio
import logging
import random
import re
from typing import TYPE_CHECKING, cast

import discord
from asgiref.sync import sync_to_async
from discord.ext import commands
from discord.utils import format_dt
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.urls import reverse

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.translation import t
from ballsdex.core.utils import checks
from ballsdex.core.utils.buttons import ConfirmChoiceView
from bd_models.models import Ball, BallInstance, Player, Special, Trade, TradeObject
from settings.models import settings
from settings.utils import format_currency

from .flags import BallsCountFlags, CreateFlags, GiveBallFlags, SpawnFlags

if TYPE_CHECKING:
    from ballsdex.packages.countryballs.cog import CountryBallsSpawner
    from ballsdex.packages.countryballs.countryball import BallSpawnView

log = logging.getLogger("ballsdex.packages.admin.balls")
FILENAME_RE = re.compile(r"^(.+)(\.\S+)$")


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
                content=t(
                    "Spawn bomb in progress in {channel}, {collectible}: {countryball}\n"
                    "{spawned}/{n} spawned ({percent}%)"
                ).format(
                    channel=channel.mention,
                    collectible=settings.collectible_name.title(),
                    countryball=countryball or "Random",
                    spawned=spawned,
                    n=n,
                    percent=round((spawned / n) * 100),
                )
            )
            await asyncio.sleep(5)
        await edit_func(content=t("Spawn bomb seems to have timed out."))

    message = await ctx.send(t("Starting spawn bomb in {channel}...").format(channel=channel.mention), ephemeral=True)
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
                    content=t(
                        "A {collectible} failed to spawn, probably indicating a lack of "
                        "permissions to send messages or upload files in {channel}."
                    ).format(collectible=settings.collectible_name, channel=channel.mention)
                )
                return
            spawned += 1
        task.cancel()
        await edit_func(
            content=t("Successfully spawned {spawned} {collectibles} in {channel}!").format(
                spawned=spawned, collectibles=settings.plural_collectible_name, channel=channel.mention
            )
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
            t(
                "The `countryballs` package is not loaded, this command is unavailable.\n"
                'Please resolve the errors preventing this package from loading. Use "{prefix}reload '
                'countryballs" to try reloading it.'
            ).format(prefix=prefix),
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
        await ctx.send(
            t("{collectible} spawned.").format(collectible=settings.collectible_name.title()), ephemeral=True
        )
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
        t(
            "`{country}` (`{id:0X}`) {collectible} was successfully given to `{user}`.\n"
            "Special: `{special}` • ATK: `{atk:+d}` • HP:`{hp:+d}` "
        ).format(
            country=flags.countryball.country,
            id=instance.pk,
            collectible=settings.collectible_name,
            user=user,
            special=flags.special.name if flags.special else None,
            atk=instance.attack_bonus,
            hp=instance.health_bonus,
        )
    )
    log.info(
        f"{ctx.author} gave {settings.collectible_name} {flags.countryball.country} (`{instance.pk:0X}`) "
        f"to {user}. (Special={flags.special.name if flags.special else None} "
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
        await ctx.send(
            t("The {collectible} ID you gave is not valid.").format(collectible=settings.collectible_name),
            ephemeral=True,
        )
        return
    try:
        ball = await BallInstance.objects.prefetch_related("player", "trade_player", "special").aget(id=pk)
    except BallInstance.DoesNotExist:
        await ctx.send(
            t("The {collectible} ID you gave does not exist.").format(collectible=settings.collectible_name),
            ephemeral=True,
        )
        return
    first_trade_object = (
        await TradeObject.objects.filter(ballinstance=ball).select_related("player").order_by("trade__date").afirst()
    )
    first_owner = first_trade_object.player if first_trade_object else ball.player
    spawned_time = format_dt(ball.spawned_time, style="R") if ball.spawned_time else "N/A"
    catch_time = (
        (ball.catch_date - ball.spawned_time).total_seconds() if ball.catch_date and ball.spawned_time else "N/A"
    )
    admin_url = f"[View online](<{reverse('admin:bd_models_ballinstance_change', args=(ball.pk,))}>)"
    await ctx.send(
        t(
            "**{collectible} ID:** {id}\n"
            "**Player:** {player}\n"
            "**First owner:** {first_owner}\n"
            "**Name:** {name}\n"
            "**Attack:** {attack}\n"
            "**Attack bonus:** {atk_bonus}\n"
            "**Health bonus:** {hp_bonus}\n"
            "**Health:** {health}\n"
            "**Special:** {special}\n"
            "**Caught at:** {catch_date}\n"
            "**Spawned at:** {spawned_time}\n"
            "**Catch time:** {catch_time} seconds\n"
            "**Caught in:** {server_id}\n"
            "**Traded:** {trade_player}\n{admin_url}"
        ).format(
            collectible=settings.collectible_name.title(),
            id=ball.pk,
            player=ball.player,
            first_owner=first_owner,
            name=ball.countryball,
            attack=ball.attack,
            atk_bonus=ball.attack_bonus,
            hp_bonus=ball.health_bonus,
            health=ball.health,
            special=ball.special.name if ball.special else None,
            catch_date=format_dt(ball.catch_date, style="R"),
            spawned_time=spawned_time,
            catch_time=catch_time,
            server_id=ball.server_id if ball.server_id else "N/A",
            trade_player=ball.trade_player,
            admin_url=admin_url,
        ),
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
        await ctx.send(
            t("The {collectible} ID you gave is not valid.").format(collectible=settings.collectible_name),
            ephemeral=True,
        )
        return
    try:
        ball = await BallInstance.objects.prefetch_related("player").aget(id=ballIdConverted)
    except BallInstance.DoesNotExist:
        await ctx.send(
            t("The {collectible} ID you gave does not exist.").format(collectible=settings.collectible_name),
            ephemeral=True,
        )
        return

    owner = await ctx.bot.fetch_user(ball.player.discord_id)

    method_label = t("soft") if soft_delete else t("hard")
    view = ConfirmChoiceView(
        ctx,
        accept_message=t("Confirmed, {method} deleting...").format(method=method_label),
        cancel_message=t("Request cancelled."),
    )
    await ctx.send(
        t("You are about to {method} delete {countryball} (ID: `{id}`) owned by `{owner}`. Are you sure?").format(
            method=method_label,
            countryball=ball.description(include_emoji=True, bot=ctx.bot),
            id=countryball_id,
            owner=owner,
        ),
        view=view,
        ephemeral=True,
    )
    await view.wait()
    if not view.value:
        return

    if soft_delete:
        ball.deleted = True
        await ball.asave()
        await ctx.send(
            t("{collectible} {id} soft deleted.").format(
                collectible=settings.collectible_name.title(), id=countryball_id
            ),
            ephemeral=True,
        )
        log.info(f"{ctx.author} soft deleted {ball}({ball.pk}).", extra={"webhook": True})
    else:
        await ball.adelete()
        await ctx.send(
            t("{collectible} {id} hard deleted.").format(
                collectible=settings.collectible_name.title(), id=countryball_id
            ),
            ephemeral=True,
        )
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
        await ctx.send(
            t("The {collectible} ID you gave is not valid.").format(collectible=settings.collectible_name),
            ephemeral=True,
        )
        return
    try:
        ball = await BallInstance.objects.prefetch_related("player").aget(id=ballIdConverted)
        original_player = ball.player
    except BallInstance.DoesNotExist:
        await ctx.send(
            t("The {collectible} ID you gave does not exist.").format(collectible=settings.collectible_name),
            ephemeral=True,
        )
        return

    original_owner = await ctx.bot.fetch_user(original_player.discord_id)

    view = ConfirmChoiceView(
        ctx, accept_message=t("Confirmed, transferring..."), cancel_message=t("Request cancelled.")
    )
    await ctx.send(
        t(
            "You are about to transfer {countryball} (ID: `{id}`) from `{original_owner}` to `{user}`. Are you sure?"
        ).format(
            countryball=ball.description(include_emoji=True, bot=ctx.bot),
            id=countryball_id,
            original_owner=original_owner,
            user=user,
        ),
        view=view,
        ephemeral=True,
    )
    await view.wait()
    if not view.value:
        return

    player, _ = await Player.objects.aget_or_create(discord_id=user.id)
    ball.player = player
    await ball.asave()

    trade = await Trade.objects.acreate(player1=original_player, player2=player)
    await TradeObject.objects.acreate(trade=trade, ballinstance=ball, player=original_player)
    await ctx.send(
        t("Transfered {countryball}({id}) from {original} to {user}.").format(
            countryball=ball, id=ball.pk, original=original_player, user=user
        ),
        ephemeral=True,
    )
    log.info(f"{ctx.author} transferred {ball}({ball.pk}) from {original_player} to {user}.", extra={"webhook": True})


@balls.command(name="transferinv")
@checks.has_permissions("bd_models.change_ballinstance")
async def balls_transferinv(
    ctx: commands.Context[BallsDexBot], source: discord.User, dest: discord.User, currency: bool = False
):
    """
    Transfer the full inventory of a user to another.

    Parameters
    ----------
    source: discord.User
        The user whose inventory you want to transfer
    dest: discord.User
        The user who should receive the inventory
    currency: bool
        Whether the player's balance should also be transferred.
    """
    if source == dest:
        await ctx.send(t("You specified the same source and destination."), ephemeral=True)
        return
    try:
        source_player = await Player.objects.aget(discord_id=source.id)
    except Player.DoesNotExist:
        await ctx.send(t("User {source} does not have a player profile.").format(source=source), ephemeral=True)
        return
    qs = BallInstance.objects.filter(player=source_player)
    balls_count = await qs.acount()
    if balls_count == 0 and (not currency or source_player.money == 0):
        await ctx.send(t("{source}'s inventory is empty.").format(source=source), ephemeral=True)
        return

    view = ConfirmChoiceView(
        ctx, accept_message=t("Confirmed, transferring..."), cancel_message=t("Request cancelled.")
    )
    if currency:
        text = t(
            "Are you sure you want to transfer {count} {collectibles} and {amount} from {source} to {dest}?"
        ).format(
            count=balls_count,
            collectibles=settings.plural_collectible_name,
            amount=format_currency(source_player.money),
            source=source,
            dest=dest,
        )
    else:
        text = t("Are you sure you want to transfer {count} {collectibles} from {source} to {dest}?").format(
            count=balls_count, collectibles=settings.plural_collectible_name, source=source, dest=dest
        )
    await ctx.send(text, view=view, ephemeral=True)
    await view.wait()
    if not view.value:
        return

    dest_player, _ = await Player.objects.aget_or_create(discord_id=dest.id)
    transferred_money = source_player.money

    @transaction.atomic
    def perform_transfer():
        trade = Trade.objects.create(
            player1=source_player, player2=dest_player, player1_money=source_player.money if currency else 0
        )
        trade_objects: list[TradeObject] = []
        for ball in qs:
            trade_objects.append(TradeObject(trade=trade, ballinstance=ball, player=source_player))
        TradeObject.objects.bulk_create(trade_objects)
        updated = qs.update(player=dest_player, trade_player=source_player)
        if currency:
            dest_player.money += source_player.money
            source_player.money = 0
            dest_player.save(update_fields=("money",))
            source_player.save(update_fields=("money",))
        return updated

    updated = await sync_to_async(perform_transfer)()

    if currency:
        text = t("{count} {collectibles} and {amount} transferred from {source} to {dest}.").format(
            count=updated,
            collectibles=settings.plural_collectible_name,
            amount=format_currency(transferred_money),
            source=source,
            dest=dest,
        )
    else:
        text = t("{count} {collectibles} transferred from {source} to {dest}.").format(
            count=updated, collectibles=settings.plural_collectible_name, source=source, dest=dest
        )
    await ctx.send(text, ephemeral=True)
    log.info(
        f"{ctx.author} transferred inventory of {source} ({source.id}, {updated} {settings.plural_collectible_name}, "
        f"{format_currency(transferred_money if currency else 0)}) to {dest} ({dest.id}).",
        extra={"webhook": True},
    )


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
        await ctx.send(t("The user you gave does not exist."), ephemeral=True)
        return
    if percentage and not 0 < percentage < 100:
        await ctx.send(t("The percentage must be between 1 and 99."), ephemeral=True)
        return
    await ctx.defer(ephemeral=True)

    method_label = t("soft") if soft_delete else t("hard")
    if not percentage:
        text = t("Are you sure you want to {method} delete {user}'s {collectibles}?").format(
            method=method_label, user=user, collectibles=settings.plural_collectible_name
        )
    else:
        text = t("Are you sure you want to {method} delete {percentage}% of {user}'s {collectibles}?").format(
            method=method_label, percentage=percentage, user=user, collectibles=settings.plural_collectible_name
        )
    view = ConfirmChoiceView(
        ctx,
        accept_message=t("Confirmed, {method} deleting the {collectibles}...").format(
            method=method_label, collectibles=settings.plural_collectible_name
        ),
        cancel_message=t("Request cancelled."),
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
    await ctx.send(
        t("{count} {collectibles} from {user} have been deleted.").format(
            count=count, collectibles=settings.plural_collectible_name, user=user
        ),
        ephemeral=True,
    )
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
    # NOTE: English-specific verb/plural suffixes, not run through ngettext - see t()'s docstring
    verb = "is" if balls == 1 else "are"
    country = f"{flags.countryball.country} " if flags.countryball else ""
    plural = "s" if balls > 1 or balls == 0 else ""
    special_str = f"{flags.special.name} " if flags.special else ""
    if flags.user:
        await ctx.send(
            t("{user} has {count} {special}{country}{collectible}{plural}.").format(
                user=flags.user,
                count=balls,
                special=special_str,
                country=country,
                collectible=settings.collectible_name,
                plural=plural,
            ),
            ephemeral=True,
        )
    else:
        await ctx.send(
            t("There {verb} {count} {special}{country}{collectible}{plural}.").format(
                verb=verb,
                count=balls,
                special=special_str,
                country=country,
                collectible=settings.collectible_name,
                plural=plural,
            ),
            ephemeral=True,
        )


@balls.command(name="create")
@checks.has_permissions("bd_models.add_ball")
async def balls_create(
    ctx: commands.Context[BallsDexBot],
    wild_card: discord.Attachment,
    collection_card: discord.Attachment,
    *,
    flags: CreateFlags,
):
    """
    Create a countryball.

    Parameters
    ----------
    wild_card: discord.Attachment
        Image used to spawn the countryball
    collection_card: discord.Attachment
        Image used when displaying countryballs
    """
    if not flags.emoji_id.isnumeric():
        await ctx.send(t("The emoji ID isn't a valid number."), ephemeral=True)
        return
    emoji = ctx.bot.get_emoji(int(flags.emoji_id))
    if not emoji:
        await ctx.send(
            t("The bot couldn't find the given emoji. Maybe it doesn't exist or the bot doesn't have access to it."),
            ephemeral=True,
        )
        return
    await ctx.defer(ephemeral=True)

    try:
        wild_card_data = await wild_card.read()
        collection_card_data = await collection_card.read()

        ball = await Ball.objects.acreate(
            country=flags.name,
            health=flags.health,
            attack=flags.attack,
            rarity=flags.rarity,
            emoji_id=emoji.id,
            credits=flags.credits,
            capacity_name=flags.capacity_name,
            capacity_description=flags.capacity_description,
            enabled=flags.enabled,
            tradeable=flags.tradeable,
            regime=flags.regime,
            economy=flags.economy,
            wild_card=ContentFile(wild_card_data, wild_card.filename),
            collection_card=ContentFile(collection_card_data, collection_card.filename),
        )
    except IntegrityError:
        log.exception(
            f"Failed creating {settings.collectible_name} because "
            f"a {settings.collectible_name} with that name ({flags.name}) already exists.",
            exc_info=True,
            extra={"webhook": True},
        )
        await ctx.send(
            t("An error occurred while creating the {collectible}. Check the error in bot logs.").format(
                collectible=settings.collectible_name
            ),
            ephemeral=True,
        )
        return
    except Exception:
        log.exception(
            f"Failed creating {settings.collectible_name} with admin command", exc_info=True, extra={"webhook": True}
        )
        await ctx.send(
            t("An error occurred while creating the {collectible}. Check the error in bot logs.").format(
                collectible=settings.collectible_name
            ),
            ephemeral=True,
        )
        return
    else:
        await ctx.bot.load_cache()
        files = [await wild_card.to_file(), await collection_card.to_file()]
        admin_url = f"[View online](<{reverse('admin:bd_models_ball_change', args=(ball.pk,))}>)"
        await ctx.send(
            t("A new {collectible} has been created! The internal cache was reloaded.\n{admin_url}\n{details}").format(
                collectible=settings.collectible_name,
                admin_url=admin_url,
                details=f"{flags.name=} regime={flags.regime.name} "
                f"economy={flags.economy.name if flags.economy else None} "
                f"{flags.health=} {flags.attack=} {flags.rarity=} {flags.enabled=} {flags.tradeable=} emoji={emoji}",
            ),
            files=files,
        )
        log.info(f'{ctx.author} created a new {settings.collectible_name} "{ball.country}"', extra={"webhook": True})
