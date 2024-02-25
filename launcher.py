from __future__ import annotations

import asyncio
import logging
import os
import sys
from enum import Enum
from pathlib import Path
from time import time
from typing import Iterable

import aiohttp
import async_timeout

try:
    import orjson
except ImportError:
    import json as orjson

import random

import uvloop
from redis import asyncio as aioredis

from ballsdex import __version__ as ballsdex_version
from ballsdex.logger import init_logger
from ballsdex.settings import read_settings, settings

log = logging.getLogger("ballsdex")

BOT_FILE = "ballsdex.py"

path = Path("config.yml")
read_settings(path)

payload = {
    "Authorization": f"Bot {settings.bot_token}",
    "User-Agent": f"Ballsdex ({ballsdex_version}, {settings.bot_name})",
}

if settings.gateway_url is None:
    GATEWAY_URL = "https://discord.com/api/gateway/bot"
    APPLICATION_URL = "https://discord.com/api/oauth2/applications/@me"
else:
    GATEWAY_URL = f"{settings.gateway_url}/gateway/bot"
    APPLICATION_URL = f"{settings.gateway_url}/oauth2/applications/@me"


async def get_gateway_info() -> int:
    async with aiohttp.ClientSession() as session:
        async with session.get(GATEWAY_URL, headers=payload) as req:
            gateway_json = await req.json()
    shard_count: int = gateway_json["shards"]
    return shard_count


async def get_app_info() -> tuple[str, int]:
    async with aiohttp.ClientSession() as session:
        async with session.get(APPLICATION_URL, headers=payload) as req:
            response = await req.json()
    return response["name"], response["id"]


def get_cluster_list(shards: int) -> list[list[int]]:
    return [
        list(range(0, shards)[i : i + settings.shards_per_cluster])
        for i in range(0, shards, settings.shards_per_cluster)
    ]


class Status(Enum):
    Initialized = "initialized"
    Running = "running"
    Stopped = "stopped"


async def _read_stream(stream):
    while True:
        line = await stream.readline()
        if line:
            log.info(line.decode("utf-8"))
        else:
            break


class Instance:
    def __init__(
        self,
        instance_id: int,
        instance_count: int,
        shard_list: list[int],
        shard_count: int,
        name: str,
        main: Main | None = None,
    ):
        self.main = main
        self.shard_count = shard_count  # overall shard count
        self.shard_list = shard_list
        self.started_at = 0.0
        self.id = instance_id
        self.instance_count = instance_count
        self.name = name
        self.command = (
            f'{sys.executable} -O {Path.cwd() / BOT_FILE} "{shard_list}" {shard_count}'
            f" {self.id} {self.instance_count} {self.name}"
        )
        self._process: asyncio.subprocess.Process | None = None
        self.status = Status.Initialized
        self.future: asyncio.Future[None] = asyncio.Future()

    @property
    def is_active(self) -> bool:
        return self._process is not None and not self._process.returncode

    def process_finished(self, stderr: bytes) -> None:
        if self._process is None:
            raise RuntimeError("This callback cannot run without a process that exited.")
        log.info(
            f"[Cluster #{self.id} ({self.name})] Exited with code" f" [{self._process.returncode}]"
        )
        if self._process.returncode == 0:
            log.info(f"[Cluster #{self.id} ({self.name})] Stopped gracefully")
            self.future.set_result(None)
        elif self.status == Status.Stopped:
            log.info(f"[Cluster #{self.id} ({self.name})] Stopped by command, not" " restarting")
            self.future.set_result(None)
        else:
            decoded_stderr = "\n".join(stderr.decode("utf-8").split("\n"))
            log.info(f"[Cluster #{self.id} ({self.name})] STDERR: {decoded_stderr}")
            log.info(f"[Cluster #{self.id} ({self.name})] Restarting...")
            asyncio.create_task(self.start())

    async def start(self) -> None:
        if self.is_active:
            log.info(f"[Cluster #{self.id} ({self.name})] The cluster is already up")
            return
        if self.main is None:
            raise RuntimeError("This cannot be possible.")
        self.started_at = time()
        log.info(self.command)
        self._process = await asyncio.create_subprocess_shell(
            self.command,
        )
        asyncio.create_task(self._run())
        log.info(f"[Cluster #{self.id}] Started successfully")
        self.status = Status.Running

    async def stop(self) -> None:
        self.status = Status.Stopped
        if self._process is None:
            raise RuntimeError("Function cannot be called before initializing the Process.")
        self._process.terminate()
        await asyncio.sleep(5)
        if self.is_active:
            self._process.kill()
            log.info(f"[Cluster #{self.id} ({self.name})] Got force killed")
        else:
            log.info(f"[Cluster #{self.id} ({self.name})] Killed gracefully")

    async def restart(self) -> None:
        if self.is_active:
            await self.stop()
        await self.start()

    async def _run(self) -> None:
        if self._process is None:
            raise RuntimeError("Function cannot be called before initializing the Process.")
        _, stderr = await self._process.communicate()
        self.process_finished(stderr)

    def __repr__(self) -> str:
        return (
            f"<Cluster ID={self.id} name={self.name}, active={self.is_active},"
            f" shards={self.shard_list}, started={self.started_at}>"
        )


class Main:
    def __init__(self) -> None:
        self.instances: list[Instance] = []
        pool = aioredis.ConnectionPool.from_url(
            f"{os.getenv('BALLSDEXBOT_REDIS_URL')}/{settings.redis_db}",
            max_connections=2,
        )
        self.redis = aioredis.Redis(connection_pool=pool)

    def get_instance(self, iterable: Iterable[Instance], id: int) -> Instance:
        for elem in iterable:
            if getattr(elem, "id") == id:
                return elem
        raise ValueError("Unknown instance")

    async def event_handler(self) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(settings.redis_subscribe)
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                payload = orjson.loads(message["data"])
            except orjson.JSONDecodeError:
                continue
            if payload.get("scope") != "launcher" or not payload.get("action"):
                continue
            args = payload.get("args", {})
            id_ = args.get("id")
            id_exists = id_ is not None
            instance = None

            if id_exists:
                try:
                    instance = self.get_instance(self.instances, id_)
                except ValueError:
                    # unknown instance
                    continue

            if payload["action"] == "restart" and instance is not None:
                log.info(f"[INFO] Restart requested for cluster #{id_}")
                asyncio.create_task(instance.restart())
            elif payload["action"] == "stop" and instance is not None:
                log.info(f"[INFO] Stop requested for cluster #{id_}")
                asyncio.create_task(instance.stop())
            elif payload["action"] == "start" and instance is not None:
                log.info(f"[INFO] Start requested for cluster #{id_}")
                asyncio.create_task(instance.start())
            elif payload["action"] == "statuses" and payload.get("command_id"):
                statuses = {}
                for instance in self.instances:
                    statuses[str(instance.id)] = {
                        "active": instance.is_active,
                        "status": instance.status.value,
                        "name": instance.name,
                        "started_at": instance.started_at,
                        "shard_list": instance.shard_list,
                    }
                await self.redis.execute_command(
                    "PUBLISH",
                    settings.redis_subscribe,
                    orjson.dumps({"command_id": payload["command_id"], "output": statuses}),
                )

    async def launch(self) -> None:
        names = [
            "Aurora",
            "Borealis",
            "Cerberus",
            "Dionysus",
            "Eos",
            "Fenrir",
            "Gaia",
            "Hades",
            "Iris",
            "Janus",
            "Khione",
            "Luna",
            "Morpheus",
            "Nyx",
            "Odin",
            "Persephone",
            "Quirinus",
            "Rhea",
            "Selene",
            "Tartarus",
            "Uranus",
            "Vesta",
            "Woden",
            "Xanthe",
            "Ymir",
            "Zeus",
        ]

        asyncio.create_task(self.event_handler())

        recommended_shard_count = await get_gateway_info()
        shard_count = recommended_shard_count + settings.extra_shards
        clusters = get_cluster_list(shard_count)
        name, _id = await get_app_info()
        log.info(f"[MAIN] Starting {name} ({_id}) - {len(clusters)} clusters")
        names = random.sample(names, len(clusters))
        for i, shard_list in enumerate(clusters):
            instance = Instance(i + 1, len(clusters), shard_list, shard_count, names[i], main=self)
            await instance.start()
            self.instances.append(instance)

        try:
            await asyncio.wait([i.future for i in self.instances])
        except (Exception, asyncio.CancelledError):
            async with async_timeout.timeout(15):
                log.info("[MAIN] Shutdown requested, stopping clusters")
                for instance in self.instances:
                    await instance.stop()


if __name__ == "__main__":
    init_logger()
    try:
        with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
            runner.run(Main().launch())
    except KeyboardInterrupt:
        pass
