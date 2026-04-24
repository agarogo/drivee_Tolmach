from __future__ import annotations

import asyncio
import logging

from app.db import PlatformSessionLocal
from app.reports.worker_runtime import get_worker_heartbeat, heartbeat_is_fresh, scheduler_worker_name
from app.wait_for_db import wait_for_database


async def _main() -> int:
    await wait_for_database(max_attempts=5)
    async with PlatformSessionLocal() as db:
        heartbeat = await get_worker_heartbeat(db, scheduler_worker_name())
        if heartbeat is None or not heartbeat_is_fresh(heartbeat.last_seen_at):
            logging.error("scheduler worker heartbeat is missing or stale")
            return 1
    logging.info("scheduler worker heartbeat is healthy")
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
