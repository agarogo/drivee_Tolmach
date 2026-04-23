import argparse
import asyncio

from app.db import AsyncSessionLocal
from app.services.bootstrap import bootstrap_demo_data


async def _run(allow_nonlocal: bool) -> None:
    async with AsyncSessionLocal() as db:
        await bootstrap_demo_data(db, allow_nonlocal=allow_nonlocal)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed local demo data for Tolmach. Disabled when APP_ENV=production.")
    parser.add_argument(
        "--allow-nonlocal",
        action="store_true",
        help="Allow seeding a non-local PostgreSQL database explicitly.",
    )
    args = parser.parse_args()
    asyncio.run(_run(allow_nonlocal=args.allow_nonlocal))


if __name__ == "__main__":
    main()
