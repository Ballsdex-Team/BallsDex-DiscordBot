import asyncio
import json
import sys

import uvloop

from ballsdex.__main__ import main as m

# Sharding stuff
shard_ids = json.loads(sys.argv[1])
shard_count = int(sys.argv[2])
cluster_id = int(sys.argv[3])
cluster_count = int(sys.argv[4])
cluster_name = sys.argv[5]


async def main() -> None:
    await m(shard_ids, shard_count, cluster_id, cluster_count, cluster_name)


if __name__ == "__main__":
    try:
        with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
            runner.run(main())
    except KeyboardInterrupt:
        pass
