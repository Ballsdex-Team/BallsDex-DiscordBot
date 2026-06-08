import logging
from typing import TYPE_CHECKING

from .cog import Merchant

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)


async def setup(bot: "BallsDexBot"):
    from merchant_app.models import GlobalShop, MerchantItem, global_shops, merchant_items

    merchant_items.clear()
    async for item in MerchantItem.objects.all():
        merchant_items[item.pk] = item

    global_shops.clear()
    async for shop in GlobalShop.objects.all():
        global_shops[shop.pk] = shop

    log.info(f"Cached {len(merchant_items)} items and {len(global_shops)} shops.")
    await bot.add_cog(Merchant(bot))
