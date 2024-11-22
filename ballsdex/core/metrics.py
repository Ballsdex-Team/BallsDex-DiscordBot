import asyncio
import logging
import math
from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.core.metrics")

caught_balls = Counter(
    "caught_cb", "Caught countryballs", ["country", "shiny", "special", "guild_size"]
)


class PrometheusServer:
    """
    Host an HTTP server for metrics collection by Prometheus.
    """

    def __init__(self, bot: "BallsDexBot", host: str = "localhost", port: int = 15260):
        self.bot = bot
        self.host = host
        self.port = port

        self.app = web.Application(logger=log)
        self.runner: web.AppRunner
        self.site: web.TCPSite
        self._inited = False

        self.app.add_routes((web.get("/metrics", self.get),))

        self.guild_count = Gauge("guilds", "Number of guilds the server is in", ["size"])
        self.shards_latecy = Histogram(
            "gateway_latency", "Shard latency with the Discord gateway", ["shard_id"]
        )
        self.asyncio_delay = Histogram(
            "asyncio_delay",
            "How much time asyncio takes to give back control",
            buckets=(
                0.001,
                0.0025,
                0.005,
                0.0075,
                0.01,
                0.025,
                0.05,
                0.075,
                0.1,
                0.25,
                0.5,
                0.75,
                1.0,
                2.5,
                5.0,
                7.5,
                10.0,
                float("inf"),
            ),
        )

    async def collect_metrics(self):
        guilds: dict[int, int] = defaultdict(int)
        for guild in self.bot.guilds:
            if not guild.member_count:
                continue
            guilds[10 ** math.ceil(math.log(max(guild.member_count - 1, 1), 10))] += 1
        for size, count in guilds.items():
            self.guild_count.labels(size=size).set(count)

        for shard_id, latency in self.bot.latencies:
            self.shards_latecy.labels(shard_id=shard_id).observe(latency)

        t1 = datetime.now()
        await asyncio.sleep(1)
        t2 = datetime.now()
        self.asyncio_delay.observe((t2 - t1).total_seconds() - 1)

    async def get(self, request: web.Request) -> web.Response:
        log.debug("Request received")
        await self.collect_metrics()
        response = web.Response(body=generate_latest())
        response.content_type = CONTENT_TYPE_LATEST
        return response

    async def setup(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host=self.host, port=self.port)
        self._inited = True

    async def run(self):
        await self.setup()
        await self.site.start()  # this call isn't blocking
        log.info(f"Prometheus server started on http://{self.site._host}:{self.site._port}/")

    async def stop(self):
        if self._inited:
            await self.site.stop()
            await self.runner.cleanup()
            log.info("Prometheus server stopped")
