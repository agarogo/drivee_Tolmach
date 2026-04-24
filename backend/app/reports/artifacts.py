from __future__ import annotations

import csv
import hashlib
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.reports.errors import ArtifactGenerationError

settings = get_settings()


@dataclass(frozen=True)
class BuiltArtifact:
    artifact_type: str
    file_name: str
    file_path: str
    content_type: str
    file_size_bytes: int
    checksum_sha256: str
    metadata_json: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "content_type": self.content_type,
            "file_size_bytes": self.file_size_bytes,
            "checksum_sha256": self.checksum_sha256,
            "metadata_json": self.metadata_json,
        }


def _artifact_root() -> Path:
    root = Path(settings.report_artifact_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run_directory(report_id: str, run_id: str) -> Path:
    directory = _artifact_root() / report_id / run_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _column_order(rows: list[dict[str, Any]]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                ordered.append(key)
    return ordered


def _build_metadata(rows: list[dict[str, Any]], chart_type: str, semantic_snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_count": len(rows),
        "columns": _column_order(rows),
        "chart_type": chart_type,
        "semantic_metric": str(semantic_snapshot.get("metric") or semantic_snapshot.get("resolved_request", {}).get("metric") or ""),
    }


def build_csv_artifact(
    *,
    report_id: str,
    run_id: str,
    title: str,
    rows: list[dict[str, Any]],
    chart_type: str,
    semantic_snapshot: dict[str, Any],
) -> BuiltArtifact:
    try:
        directory = _run_directory(report_id, run_id)
        path = directory / "result.csv"
        columns = _column_order(rows)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
    except Exception as exc:
        raise ArtifactGenerationError("Failed to build CSV artifact.", details={"title": title}) from exc
    return BuiltArtifact(
        artifact_type="csv",
        file_name=path.name,
        file_path=str(path),
        content_type="text/csv",
        file_size_bytes=path.stat().st_size,
        checksum_sha256=_checksum(path),
        metadata_json=_build_metadata(rows, chart_type, semantic_snapshot),
    )


def build_json_artifact(
    *,
    report_id: str,
    run_id: str,
    title: str,
    rows: list[dict[str, Any]],
    chart_type: str,
    semantic_snapshot: dict[str, Any],
) -> BuiltArtifact:
    try:
        directory = _run_directory(report_id, run_id)
        path = directory / "result.json"
        payload = {
            "title": title,
            "row_count": len(rows),
            "chart_type": chart_type,
            "semantic_snapshot": semantic_snapshot,
            "rows": rows,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        raise ArtifactGenerationError("Failed to build JSON artifact.", details={"title": title}) from exc
    return BuiltArtifact(
        artifact_type="json",
        file_name=path.name,
        file_path=str(path),
        content_type="application/json",
        file_size_bytes=path.stat().st_size,
        checksum_sha256=_checksum(path),
        metadata_json=_build_metadata(rows, chart_type, semantic_snapshot),
    )


def build_html_artifact(
    *,
    report_id: str,
    run_id: str,
    title: str,
    rows: list[dict[str, Any]],
    chart_type: str,
    semantic_snapshot: dict[str, Any],
) -> BuiltArtifact:
    try:
        directory = _run_directory(report_id, run_id)
        path = directory / "summary.html"
        columns = _column_order(rows)
        header_html = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
        rows_html = "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns) + "</tr>"
            for row in rows[:100]
        )
        metric = html.escape(str(semantic_snapshot.get("metric") or semantic_snapshot.get("resolved_request", {}).get("metric") or ""))
        content = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{html.escape(title)}</title>
    <style>
      body {{ font-family: Arial, sans-serif; background: #f8faf8; color: #112016; padding: 24px; }}
      h1 {{ margin-bottom: 8px; }}
      .meta {{ color: #4a5a4d; margin-bottom: 16px; }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ border: 1px solid #d6ded8; padding: 8px; text-align: left; }}
      th {{ background: #e8efe9; }}
    </style>
  </head>
  <body>
    <h1>{html.escape(title)}</h1>
    <div class="meta">Chart: {html.escape(chart_type)} | Semantic metric: {metric} | Rows: {len(rows)}</div>
    <table>
      <thead><tr>{header_html}</tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </body>
</html>
"""
        path.write_text(content, encoding="utf-8")
    except Exception as exc:
        raise ArtifactGenerationError("Failed to build HTML artifact.", details={"title": title}) from exc
    return BuiltArtifact(
        artifact_type="html",
        file_name=path.name,
        file_path=str(path),
        content_type="text/html",
        file_size_bytes=path.stat().st_size,
        checksum_sha256=_checksum(path),
        metadata_json=_build_metadata(rows, chart_type, semantic_snapshot),
    )


def build_report_artifacts(
    *,
    report_id: str,
    run_id: str,
    title: str,
    rows: list[dict[str, Any]],
    chart_type: str,
    semantic_snapshot: dict[str, Any],
) -> list[BuiltArtifact]:
    return [
        build_csv_artifact(
            report_id=report_id,
            run_id=run_id,
            title=title,
            rows=rows,
            chart_type=chart_type,
            semantic_snapshot=semantic_snapshot,
        ),
        build_json_artifact(
            report_id=report_id,
            run_id=run_id,
            title=title,
            rows=rows,
            chart_type=chart_type,
            semantic_snapshot=semantic_snapshot,
        ),
        build_html_artifact(
            report_id=report_id,
            run_id=run_id,
            title=title,
            rows=rows,
            chart_type=chart_type,
            semantic_snapshot=semantic_snapshot,
        ),
    ]
