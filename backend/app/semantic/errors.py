from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SemanticErrorCode(str, Enum):
    UNKNOWN_METRIC = "unknown_metric"
    METRIC_REQUIRED = "metric_required"
    UNSUPPORTED_GRAIN = "unsupported_grain"
    UNKNOWN_DIMENSION = "unknown_dimension"
    DISALLOWED_DIMENSION = "disallowed_dimension"
    UNKNOWN_FILTER = "unknown_filter"
    DISALLOWED_FILTER = "disallowed_filter"
    INVALID_FILTER_OPERATOR = "invalid_filter_operator"
    MISSING_FILTER_VALUES = "missing_filter_values"
    INVALID_FILTER_VALUE = "invalid_filter_value"
    INVALID_PERIOD = "invalid_period"
    INVALID_LIMIT = "invalid_limit"
    INVALID_SORT = "invalid_sort"
    INVALID_METRIC_TEMPLATE = "invalid_metric_template"
    INVALID_DIMENSION_TEMPLATE = "invalid_dimension_template"
    INVALID_JOIN_PATH = "invalid_join_path"
    SQL_PARSE_ERROR = "sql_parse_error"
    MULTI_STATEMENT = "multi_statement"
    NON_READONLY_STATEMENT = "non_readonly_statement"
    WRITE_OPERATION = "write_operation"
    DDL_OPERATION = "ddl_operation"
    UNKNOWN_TABLE = "unknown_table"
    ACCESS_POLICY_MISSING = "access_policy_missing"
    UNKNOWN_COLUMN = "unknown_column"
    FORBIDDEN_COLUMN = "forbidden_column"
    SELECT_STAR = "select_star"
    LIMIT_INJECTED = "limit_injected"
    LIMIT_CAPPED = "limit_capped"
    EXPLAIN_FAILED = "explain_failed"
    EXPLAIN_COST_EXCEEDED = "explain_cost_exceeded"


class ClarificationCode(str, Enum):
    AMBIGUOUS_REQUEST = "ambiguous_request"
    METRIC_REQUIRED = "metric_required"
    METRIC_NOT_IN_CATALOG = "metric_not_in_catalog"
    DIMENSION_NOT_IN_CATALOG = "dimension_not_in_catalog"
    FILTER_NOT_IN_CATALOG = "filter_not_in_catalog"
    PERIOD_REQUIRED = "period_required"


@dataclass(frozen=True)
class StructuredReason:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True)
class BlockReason(StructuredReason):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClarificationReason(StructuredReason):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class SemanticCompilationError(ValueError):
    def __init__(self, reason: BlockReason):
        super().__init__(reason.message)
        self.reason = reason


def build_block_reason(
    code: SemanticErrorCode | str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> BlockReason:
    normalized_code = code.value if isinstance(code, Enum) else str(code)
    return BlockReason(code=normalized_code, message=message, details=details or {})


def build_clarification_reason(
    code: ClarificationCode | str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> ClarificationReason:
    normalized_code = code.value if isinstance(code, Enum) else str(code)
    return ClarificationReason(code=normalized_code, message=message, details=details or {})
