from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReportRuntimeError(RuntimeError):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


class ReportValidationError(ReportRuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="report_validation_failed",
            message=message,
            retryable=False,
            details=details or {},
        )


class ArtifactGenerationError(ReportRuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="artifact_generation_failed",
            message=message,
            retryable=False,
            details=details or {},
        )


class DeliveryConfigurationError(ReportRuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="delivery_configuration_error",
            message=message,
            retryable=False,
            details=details or {},
        )


class DeliveryTransportError(ReportRuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="delivery_transport_error",
            message=message,
            retryable=True,
            details=details or {},
        )
