from __future__ import annotations

import hashlib
import re

from app.config import get_settings

settings = get_settings()


def normalize_sql_for_fingerprint(sql: str) -> str:
    normalized = re.sub(r"\s+", " ", sql.strip().rstrip(";"))
    return normalized.lower()


def build_query_fingerprint(sql: str, role: str) -> str:
    payload = f"{settings.query_cache_namespace}|{role.strip().lower()}|{normalize_sql_for_fingerprint(sql)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
