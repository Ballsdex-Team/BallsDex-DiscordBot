import logging
import random
from typing import TYPE_CHECKING

from currency_app.models import BerryTransaction
from django.db.models import F
from django.utils import timezone
from merchant_app.models import MerchantItem, merchant_items

from bd_models.models import BallInstance, Player
from settings.models import settings
from settings.utils import format_currency

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)


class PurchaseError(Exception):
    """
    The purchase could not go through, the message is meant to be shown to the player.
    """


async def _release_stock(item: MerchantItem):
    await MerchantItem.objects.filter(pk=item.pk, stock__isnull=False).aupdate(stock=F("stock") + 1)


async def _refresh_cached_stock(item: MerchantItem):
    stock = await MerchantItem.objects.filter(pk=item.pk).values_list("stock", flat=True).afirst()
    item.stock = stock
    if cached := merchant_items.get(item.pk):
        cached.stock = stock


async def buy_item(
    bot: "BallsDexBot", player: Player, item: MerchantItem, *, server_id: int | None = None
) -> BallInstance:
    """
    Buy a merchant item for a player: take one unit of stock if the item is limited, take the berries,
    then give the treasure. Every step is reverted if a later one fails.

    Raises
    ------
    PurchaseError
        The purchase failed, with a message explaining why.
    """
    reserved = False
    if item.stock is not None:
        # decrementing only when some stock is left is atomic, two players can't buy the last unit
        reserved = await MerchantItem.objects.filter(pk=item.pk, stock__gt=0).aupdate(stock=F("stock") - 1) > 0
        if not reserved:
            await _refresh_cached_stock(item)
            raise PurchaseError(f"**{item.name}** is sold out!")

    try:
        if item.prize:
            try:
                await player.remove_money(
                    item.prize,
                    reason=BerryTransaction.Reason.MERCHANT_BUY,
                    description=f"Bought {item.name} from the merchant",
                    server_id=server_id,
                )
            except ValueError:
                await player.arefresh_from_db(fields=("money",))
                raise PurchaseError(
                    f"You don't have enough {settings.currency_display_plural(bot)} to buy **{item.name}**\n"
                    f"Your actual balance: {format_currency(player.money, False, bot)}"
                )

        try:
            instance = await BallInstance.objects.acreate(
                player=player,
                ball=item.cached_ball,
                special=item.cached_special,
                health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
                attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
                catch_date=timezone.now(),
                server_id=server_id,
            )
        except Exception:
            log.exception("Failed to create a ball instance while a user was buying an item.")
            if item.prize:
                await player.add_money(
                    item.prize,
                    reason=BerryTransaction.Reason.MERCHANT_BUY,
                    description=f"Refunded {item.name}, the purchase failed",
                    server_id=server_id,
                )
            raise PurchaseError("An error occurred while trying to buy the item.")
    except PurchaseError:
        if reserved:
            await _release_stock(item)
        raise

    if reserved:
        await _refresh_cached_stock(item)
    return instance


def purchase_message(bot: "BallsDexBot", item: MerchantItem, instance: BallInstance) -> str:
    price = f"**{format_currency(item.prize, False, bot)}!**" if item.prize else "**free!**"
    text = f"You've bought {item.name} for {price}\n{instance.description(include_emoji=True, bot=bot)}"
    if item.stock is not None:
        text += f"\n-# {item.stock_text}"
    return text
