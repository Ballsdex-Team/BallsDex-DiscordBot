from typing import Iterable

from collector_app.models import Collector
from discord import app_commands

from ballsdex.core.utils.transformers import TTLModelTransformer


class CollectorTransformer(TTLModelTransformer[Collector]):
    name = "collector"
    model = Collector

    async def get_from_pk(self, value: int) -> Collector:
        return await self.get_queryset().aget(pk=value)


class CollectorEnabledTransformer(CollectorTransformer):
    async def load_items(self) -> Iterable[Collector]:
        # each collector shows up once, its tiers are picked afterwards
        queryset = Collector.objects.filter(tiers__enabled=True).distinct()
        return [collector async for collector in queryset if collector.active]


CollectorTransform = app_commands.Transform[Collector, CollectorTransformer]
CollectorEnabledTransform = app_commands.Transform[Collector, CollectorEnabledTransformer]
