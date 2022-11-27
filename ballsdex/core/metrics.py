import logging

from aiohttp import web
from prometheus_client import Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.core.metrics")


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

        self.guild_count = Gauge("guilds", "Number of guilds the server is in")
        self.shards_latecy = Histogram(
            "gateway_latency", "Shard latency with the Discord gateway", ["shard_id"]
        )

    async def collect_metrics(self):
        self.guild_count.set(len(self.bot.guilds))

        for shard_id, latency in self.bot.latencies:
            self.shards_latecy.labels(shard_id=shard_id).observe(latency)

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
