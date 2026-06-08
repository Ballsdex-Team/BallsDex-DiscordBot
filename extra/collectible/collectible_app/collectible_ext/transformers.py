from typing import Iterable

from discord import app_commands

from ballsdex.core.utils.transformers import TTLModelTransformer
from collectible_app.models import Collectible


class CollectibleTransformer(TTLModelTransformer[Collectible]):
    name = "collectible"
    model = Collectible

    def get_queryset(self):
        return super().get_queryset().prefetch_related("ball", "special")

    async def get_from_pk(self, value: int) -> Collectible:
        return await self.get_queryset().prefetch_related("ball", "special").aget(pk=value)

    async def load_items(self) -> Iterable[Collectible]:
        return [x async for x in Collectible.objects.all()]


CollectibleTransform = app_commands.Transform[Collectible, CollectibleTransformer]
