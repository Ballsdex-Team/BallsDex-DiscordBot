from typing import Iterable

from discord import app_commands
from merchant_app.models import GlobalShop, global_shops

from ballsdex.core.utils.transformers import TTLModelTransformer


class GlobalShopTransformer(TTLModelTransformer[GlobalShop]):
    name = "global shop"
    model = GlobalShop

    async def get_from_pk(self, value: int) -> GlobalShop:
        return await self.get_queryset().prefetch_related("items").aget(pk=value)

    async def load_items(self) -> Iterable[GlobalShop]:
        return global_shops.values()


GlobalShopTransform = app_commands.Transform[GlobalShop, GlobalShopTransformer]
