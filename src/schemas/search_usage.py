# -*- coding: utf-8 -*-
"""Internal contracts for physical search-provider request auditing."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from enum import Enum
import threading
import uuid
from typing import Any, Dict, Iterator, Optional


class SearchErrorCategory(str, Enum):
    QUOTA_EXHAUSTED = "quota_exhausted"
    AUTH_INVALID = "auth_invalid"
    PERMISSION_DENIED = "permission_denied"
    ACCOUNT_DISABLED = "account_disabled"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    PROVIDER_5XX = "provider_5xx"
    INVALID_RESPONSE = "invalid_response"
    OTHER = "other"


@dataclass
class SearchAuditContext:
    business_search_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    logical_request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    call_source: str = "direct"
    operation: str = "search"
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None
    dimension: Optional[str] = None
    lookback_days: Optional[int] = None
    provider_attempt: int = 1
    _physical_attempt: int = field(default=0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def next_physical_attempt(self) -> int:
        with self._lock:
            self._physical_attempt += 1
            return self._physical_attempt

    def child(self, **updates: Any) -> "SearchAuditContext":
        updates.setdefault("logical_request_id", uuid.uuid4().hex)
        updates.setdefault("_physical_attempt", 0)
        updates.setdefault("_lock", threading.Lock())
        return replace(self, **updates)

    def public_dict(self) -> Dict[str, Any]:
        return {
            "business_search_id": self.business_search_id,
            "logical_request_id": self.logical_request_id,
            "call_source": self.call_source,
            "operation": self.operation,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "dimension": self.dimension,
            "lookback_days": self.lookback_days,
            "provider_attempt": self.provider_attempt,
        }


_SEARCH_AUDIT_CONTEXT: ContextVar[Optional[SearchAuditContext]] = ContextVar(
    "search_audit_context",
    default=None,
)


def current_search_audit_context() -> Optional[SearchAuditContext]:
    return _SEARCH_AUDIT_CONTEXT.get()


@contextmanager
def search_audit_scope(context: SearchAuditContext) -> Iterator[SearchAuditContext]:
    token = _SEARCH_AUDIT_CONTEXT.set(context)
    try:
        yield context
    finally:
        _SEARCH_AUDIT_CONTEXT.reset(token)
