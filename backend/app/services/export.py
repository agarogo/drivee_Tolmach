from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any


def rows_to_csv(rows: Iterable[Mapping[str, Any]]) -> str:
    rows_list = [dict(row) for row in rows]
    output = io.StringIO()
    if not rows_list:
        return ""
    fieldnames: list[str] = []
    for row in rows_list:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows_list:
        writer.writerow(row)
    return output.getvalue()
