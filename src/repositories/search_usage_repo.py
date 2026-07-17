# -*- coding: utf-8 -*-
"""Persistence helpers for search-provider usage auditing."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from sqlalchemy import and_, desc, distinct, func, or_, select

from src.storage import (
    DatabaseManager,
    SearchApiCall,
    SearchAuditGap,
    SearchProviderFault,
)


class SearchUsageRepository:
    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager.get_instance()

    def insert_call(self, values: Dict[str, Any]) -> int:
        row = SearchApiCall(**values)
        with self.db.session_scope() as session:
            session.add(row)
            session.flush()
            return int(row.id)

    def insert_gap(
        self,
        *,
        lost_count: int,
        first_failed_at: datetime,
        last_failed_at: datetime,
        error_summary: Optional[str],
    ) -> None:
        with self.db.session_scope() as session:
            session.add(
                SearchAuditGap(
                    lost_count=max(1, int(lost_count)),
                    first_failed_at=first_failed_at,
                    last_failed_at=last_failed_at,
                    error_summary=error_summary,
                )
            )

    @staticmethod
    def _filters(
        *,
        from_dt: datetime,
        to_dt: datetime,
        provider: Optional[str] = None,
        call_source: Optional[str] = None,
        success: Optional[bool] = None,
        error_category: Optional[str] = None,
        key_fingerprint: Optional[str] = None,
    ) -> List[Any]:
        filters: List[Any] = [
            SearchApiCall.requested_at >= from_dt,
            SearchApiCall.requested_at <= to_dt,
        ]
        if provider:
            filters.append(SearchApiCall.provider == provider)
        if call_source:
            filters.append(SearchApiCall.call_source == call_source)
        if success is not None:
            filters.append(SearchApiCall.success.is_(bool(success)))
        if error_category:
            filters.append(SearchApiCall.error_category == error_category)
        if key_fingerprint:
            filters.append(SearchApiCall.key_fingerprint == key_fingerprint)
        return filters

    def summary(self, **filters: Any) -> Dict[str, Any]:
        where = self._filters(**filters)
        with self.db.session_scope() as session:
            row = session.execute(
                select(
                    func.count(SearchApiCall.id),
                    func.count(distinct(SearchApiCall.business_search_id)),
                    func.coalesce(func.sum(func.cast(SearchApiCall.success, type_=SearchApiCall.id.type)), 0),
                ).where(and_(*where))
            ).one()
        total = int(row[0] or 0)
        success_count = int(row[2] or 0)
        return {
            "physical_requests": total,
            "business_searches": int(row[1] or 0),
            "success_count": success_count,
            "failure_count": max(0, total - success_count),
            "success_rate": round(success_count / total, 4) if total else 0.0,
        }

    def breakdown(self, field_name: str, **filters: Any) -> List[Dict[str, Any]]:
        columns = {
            "provider": SearchApiCall.provider,
            "key_fingerprint": SearchApiCall.key_fingerprint,
            "call_source": SearchApiCall.call_source,
            "error_category": SearchApiCall.error_category,
        }
        column = columns[field_name]
        where = self._filters(**filters)
        with self.db.session_scope() as session:
            rows = session.execute(
                select(column, func.count(SearchApiCall.id))
                .where(and_(*where))
                .group_by(column)
                .order_by(desc(func.count(SearchApiCall.id)))
            ).all()
        return [{"value": value or "unknown", "count": int(count)} for value, count in rows]

    def list_calls(self, *, page: int, page_size: int, **filters: Any) -> Dict[str, Any]:
        where = self._filters(**filters)
        with self.db.session_scope() as session:
            total = int(session.execute(select(func.count(SearchApiCall.id)).where(and_(*where))).scalar_one())
            rows = session.execute(
                select(SearchApiCall)
                .where(and_(*where))
                .order_by(desc(SearchApiCall.requested_at), desc(SearchApiCall.id))
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars().all()
            items = [self._call_summary(row) for row in rows]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def iter_calls(self, *, batch_size: int = 500, **filters: Any) -> Iterator[Dict[str, Any]]:
        where = self._filters(**filters)
        offset = 0
        while True:
            with self.db.session_scope() as session:
                rows = session.execute(
                    select(SearchApiCall)
                    .where(and_(*where))
                    .order_by(SearchApiCall.requested_at, SearchApiCall.id)
                    .offset(offset)
                    .limit(batch_size)
                ).scalars().all()
                batch = [self._call_summary(row) for row in rows]
            if not batch:
                return
            yield from batch
            offset += len(batch)

    def get_call(self, call_id: int) -> Optional[Dict[str, Any]]:
        with self.db.session_scope() as session:
            row = session.get(SearchApiCall, int(call_id))
            return self._call_detail(row) if row is not None else None

    def audit_started_at(self) -> Optional[datetime]:
        with self.db.session_scope() as session:
            return session.execute(select(func.min(SearchApiCall.requested_at))).scalar_one_or_none()

    def audit_gap_totals(self) -> Dict[str, Any]:
        with self.db.session_scope() as session:
            row = session.execute(
                select(
                    func.coalesce(func.sum(SearchAuditGap.lost_count), 0),
                    func.max(SearchAuditGap.last_failed_at),
                )
            ).one()
        return {"persisted_lost_count": int(row[0] or 0), "last_gap_at": row[1]}

    def record_fault_event(
        self,
        *,
        provider: str,
        key_fingerprint: str,
        category: str,
        occurred_at: datetime,
        call_id: int,
        error_summary: Optional[str],
        immediate: bool,
        transient_window: timedelta,
        threshold: int,
    ) -> Tuple[Dict[str, Any], bool]:
        activated = False
        with self.db.session_scope() as session:
            row = session.execute(
                select(SearchProviderFault).where(
                    SearchProviderFault.provider == provider,
                    SearchProviderFault.key_fingerprint == key_fingerprint,
                    SearchProviderFault.error_category == category,
                )
            ).scalar_one_or_none()
            if row is None:
                row = SearchProviderFault(
                    provider=provider,
                    key_fingerprint=key_fingerprint,
                    error_category=category,
                    active=False,
                    first_seen_at=occurred_at,
                    last_seen_at=occurred_at,
                    window_started_at=occurred_at,
                    consecutive_count=0,
                )
                session.add(row)
            if row.window_started_at is None or occurred_at - row.window_started_at > transient_window:
                row.window_started_at = occurred_at
                row.consecutive_count = 0
            row.last_seen_at = occurred_at
            row.last_call_id = call_id
            row.last_error_summary = error_summary
            row.consecutive_count = int(row.consecutive_count or 0) + 1
            should_activate = immediate or row.consecutive_count >= threshold
            if should_activate and not row.active:
                row.active = True
                row.resolved_at = None
                row.recovery_notified_at = None
                row.first_seen_at = occurred_at
                activated = True
            session.flush()
            result = self._fault_dict(row)
        return result, activated

    def resolve_faults(self, provider: str, key_fingerprint: str, resolved_at: datetime) -> List[Dict[str, Any]]:
        resolved: List[Dict[str, Any]] = []
        with self.db.session_scope() as session:
            rows = session.execute(
                select(SearchProviderFault).where(
                    SearchProviderFault.provider == provider,
                    SearchProviderFault.key_fingerprint == key_fingerprint,
                )
            ).scalars().all()
            for row in rows:
                was_active = bool(row.active)
                if was_active:
                    row.active = False
                    row.resolved_at = resolved_at
                row.consecutive_count = 0
                row.window_started_at = None
                if was_active:
                    resolved.append(self._fault_dict(row))
        return resolved

    def resolve_removed_keys(self, configured: Dict[str, Sequence[str]], resolved_at: datetime) -> List[Dict[str, Any]]:
        resolved: List[Dict[str, Any]] = []
        with self.db.session_scope() as session:
            rows = session.execute(
                select(SearchProviderFault).where(SearchProviderFault.active.is_(True))
            ).scalars().all()
            for row in rows:
                configured_keys = set(configured.get(row.provider, ()))
                if row.key_fingerprint not in configured_keys:
                    row.active = False
                    row.resolved_at = resolved_at
                    row.consecutive_count = 0
                    row.window_started_at = None
                    resolved.append(self._fault_dict(row))
        return resolved

    def list_active_faults(self) -> List[Dict[str, Any]]:
        with self.db.session_scope() as session:
            rows = session.execute(
                select(SearchProviderFault)
                .where(SearchProviderFault.active.is_(True))
                .order_by(desc(SearchProviderFault.last_seen_at))
            ).scalars().all()
            return [self._fault_dict(row) for row in rows]

    def claim_notification(self, fault_id: int, *, recovery: bool, now: datetime, cooldown: timedelta) -> bool:
        with self.db.session_scope() as session:
            row = session.get(SearchProviderFault, int(fault_id))
            if row is None:
                return False
            if recovery:
                if row.recovery_notified_at is not None:
                    return False
                row.recovery_notified_at = now
            else:
                if row.last_notified_at is not None and now - row.last_notified_at < cooldown:
                    return False
                row.last_notified_at = now
            row.last_notification_status = "pending"
            return True

    def update_notification_status(self, fault_id: int, status: str) -> None:
        with self.db.session_scope() as session:
            row = session.get(SearchProviderFault, int(fault_id))
            if row is not None:
                row.last_notification_status = str(status or "unknown")[:64]

    @staticmethod
    def _call_summary(row: SearchApiCall) -> Dict[str, Any]:
        return {
            "id": row.id,
            "business_search_id": row.business_search_id,
            "logical_request_id": row.logical_request_id,
            "provider": row.provider,
            "endpoint": row.endpoint,
            "http_method": row.http_method,
            "call_source": row.call_source,
            "operation": row.operation,
            "stock_code": row.stock_code,
            "stock_name": row.stock_name,
            "dimension": row.dimension,
            "lookback_days": row.lookback_days,
            "provider_attempt": row.provider_attempt,
            "physical_attempt": row.physical_attempt,
            "key_fingerprint": row.key_fingerprint,
            "success": row.success,
            "http_status": row.http_status,
            "provider_code": row.provider_code,
            "provider_request_id": row.provider_request_id,
            "duration_ms": row.duration_ms,
            "result_count": row.result_count,
            "error_category": row.error_category,
            "error_summary": row.error_summary,
            "request_truncated": row.request_truncated,
            "request_size_bytes": row.request_size_bytes,
            "request_sha256": row.request_sha256,
            "response_truncated": row.response_truncated,
            "response_size_bytes": row.response_size_bytes,
            "response_sha256": row.response_sha256,
            "requested_at": row.requested_at,
            "completed_at": row.completed_at,
        }

    @classmethod
    def _call_detail(cls, row: SearchApiCall) -> Dict[str, Any]:
        result = cls._call_summary(row)
        result.update(
            {
                "trace_id": row.trace_id,
                "query_hmac": row.query_hmac,
                "request_snapshot_json": row.request_snapshot_json,
                "response_snapshot_json": row.response_snapshot_json,
            }
        )
        return result

    @staticmethod
    def _fault_dict(row: SearchProviderFault) -> Dict[str, Any]:
        return {
            "id": row.id,
            "provider": row.provider,
            "key_fingerprint": row.key_fingerprint,
            "error_category": row.error_category,
            "active": row.active,
            "severity": row.severity,
            "first_seen_at": row.first_seen_at,
            "last_seen_at": row.last_seen_at,
            "resolved_at": row.resolved_at,
            "consecutive_count": row.consecutive_count,
            "last_notified_at": row.last_notified_at,
            "last_notification_status": row.last_notification_status,
            "recovery_notified_at": row.recovery_notified_at,
            "last_error_summary": row.last_error_summary,
            "last_call_id": row.last_call_id,
        }
