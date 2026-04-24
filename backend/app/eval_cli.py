from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "evals" / "nl_sql_cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    print(f"Loaded {len(cases)} NL→SQL evaluation cases from {path}")
    for case in cases:
        print(f"- {case['id']}: {case['question']}")


if __name__ == "__main__":
    main()
