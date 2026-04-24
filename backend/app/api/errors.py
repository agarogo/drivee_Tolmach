from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict[str, Any] = field(default_factory=dict)

    def as_payload(self, request_id: str | None = None) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "request_id": request_id,
            }
        }


class NotFoundError(AppError):
    def __init__(self, message: str = "Ресурс не найден", details: dict[str, Any] | None = None):
        super().__init__(code="NOT_FOUND", message=message, status_code=404, details=details or {})


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "Недостаточно прав", details: dict[str, Any] | None = None):
        super().__init__(code="PERMISSION_DENIED", message=message, status_code=403, details=details or {})


class GuardrailBlockedApiError(AppError):
    def __init__(self, message: str = "Запрос заблокирован правилами безопасности", details: dict[str, Any] | None = None):
        super().__init__(code="SQL_GUARDRAIL_BLOCKED", message=message, status_code=400, details=details or {})
