from datetime import datetime
from typing import Iterable

from collector_app.models import Collector
from discord import app_commands
from django.utils import timezone

from ballsdex.core.utils.transformers import TTLModelTransformer


class CollectorTransformer(TTLModelTransformer[Collector]):
    name = "collector"
    model = Collector

    async def get_from_pk(self, value: int) -> Collector:
        return await self.get_queryset().prefetch_related("requirements").aget(pk=value)


class CollectorEnabledTransformer(CollectorTransformer):
    async def load_items(self) -> Iterable[Collector]:
        return [
            x
            async for x in Collector.objects.all()
            if (x.start_date or datetime.min.replace(tzinfo=timezone.get_default_timezone()))
            <= timezone.now()
            <= (x.end_date or datetime.max.replace(tzinfo=timezone.get_default_timezone()))
        ]


CollectorTransform = app_commands.Transform[Collector, CollectorTransformer]
CollectorEnabledTransform = app_commands.Transform[Collector, CollectorEnabledTransformer]
