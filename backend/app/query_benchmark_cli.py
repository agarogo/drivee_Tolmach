from __future__ import annotations

import argparse
import asyncio
import json

from app.config import get_settings
from app.db import PlatformSessionLocal
from app.query_execution.benchmarks import run_benchmark_suite

settings = get_settings()


async def _run(iterations: int, role: str) -> None:
    async with PlatformSessionLocal() as db:
        payload = await run_benchmark_suite(db, iterations=iterations, role=role)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run safe query execution benchmarks for governed analytics queries.")
    parser.add_argument("--iterations", type=int, default=settings.benchmark_default_iterations)
    parser.add_argument("--role", type=str, default="admin")
    args = parser.parse_args()
    asyncio.run(_run(iterations=max(2, args.iterations), role=args.role.strip().lower() or "admin"))


if __name__ == "__main__":
    main()
