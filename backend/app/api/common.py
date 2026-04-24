"""Compatibility re-exports for older code.

New route modules should import explicitly from:
- app.api.deps
- app.api.utils
- app.repositories.*
"""
from __future__ import annotations

from app.api.deps import get_current_user, get_db, require_admin
from app.api.utils import (
    _device_hint,
    _run_query_workflow_or_503,
    assistant_payload_from_query,
    chat_out,
    device_hint,
    query_to_out,
    report_to_out,
    run_query_workflow_or_503,
    run_to_out,
    schedule_to_out,
    to_user_out,
)
from app.repositories import (
    delete_chat_with_related_data,
    ensure_query_chat,
    make_chat_title,
    require_owned_chat,
    require_owned_query,
    require_owned_report,
    require_owned_schedule,
)

__all__ = [name for name in globals() if not name.startswith("_") or name in {"_device_hint", "_run_query_workflow_or_503"}]
