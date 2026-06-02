from currency_app.models import Item
from discord import app_commands

from ballsdex.core.utils.transformers import TTLModelTransformer


class ItemTransformer(TTLModelTransformer[Item]):
    name = "item"
    model = Item

    def key(self, model: Item) -> str:
        return model.name

    async def get_from_pk(self, value: int) -> Item:
        return await self.get_queryset().prefetch_related("special", "balls").aget(pk=value)


ItemTransform = app_commands.Transform[Item, ItemTransformer]
