import asyncio
import logging

from app.reports.scheduler import scheduler_loop
from app.wait_for_db import wait_for_database


async def _main() -> None:
    await wait_for_database()
    await scheduler_loop()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())


if __name__ == "__main__":
    main()
