# -*- coding: utf-8 -*-
"""Business logic for search-provider usage, faults, exports, and alerts."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import io
import json
import logging
import threading
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from src.config import get_config
from src.llm.usage import build_domain_hmac
from src.repositories.search_usage_repo import SearchUsageRepository
from src.schemas.search_usage import SearchErrorCategory
from src.utils.sanitize import sanitize_diagnostic_text


logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))
_IMMEDIATE_FAULTS = {
    SearchErrorCategory.QUOTA_EXHAUSTED.value,
    SearchErrorCategory.AUTH_INVALID.value,
    SearchErrorCategory.PERMISSION_DENIED.value,
    SearchErrorCategory.ACCOUNT_DISABLED.value,
}
_TRANSIENT_FAULTS = {
    SearchErrorCategory.RATE_LIMITED.value,
    SearchErrorCategory.TIMEOUT.value,
    SearchErrorCategory.CONNECTION_ERROR.value,
    SearchErrorCategory.PROVIDER_5XX.value,
}
_PROVIDER_CONFIG_FIELDS = {
    "Anspire": "anspire_api_keys",
    "Bocha": "bocha_api_keys",
    "Tavily": "tavily_api_keys",
    "Brave": "brave_api_keys",
    "SerpAPI": "serpapi_api_keys",
    "MiniMax": "minimax_api_keys",
    "SearXNG": "searxng_base_urls",
}

_GAP_LOCK = threading.RLock()
_GAP_COUNT = 0
_GAP_FIRST_AT: Optional[datetime] = None
_GAP_LAST_AT: Optional[datetime] = None
_GAP_LAST_ERROR: Optional[str] = None


def fingerprint_search_value(value: Any, *, domain: str) -> str:
    digest = build_domain_hmac(value, domain=domain).get("hmac")
    return str(digest or "unavailable")


class SearchUsageService:
    def __init__(self, repo: Optional[SearchUsageRepository] = None):
        self.repo = repo or SearchUsageRepository()

    def record_physical_call(self, values: Dict[str, Any]) -> Optional[int]:
        """Synchronously persist a call; fail open while making audit gaps visible."""
        try:
            call_id = self.repo.insert_call(values)
        except Exception as exc:
            self._remember_gap(exc)
            logger.error(
                "[Search audit] 调用记录写入失败 provider=%s logical_request_id=%s: %s",
                values.get("provider"),
                values.get("logical_request_id"),
                sanitize_diagnostic_text(exc),
                exc_info=True,
            )
            return None

        self._flush_remembered_gap()
        try:
            self._update_fault_state(call_id, values)
        except Exception as exc:
            logger.error(
                "[Search audit] 故障状态更新失败 call_id=%s: %s",
                call_id,
                sanitize_diagnostic_text(exc),
                exc_info=True,
            )
        return call_id

    def _update_fault_state(self, call_id: int, values: Dict[str, Any]) -> None:
        provider = str(values.get("provider") or "Unknown")
        key_fingerprint = str(values.get("key_fingerprint") or "unavailable")
        occurred_at = values.get("completed_at") or datetime.now(timezone.utc).replace(tzinfo=None)
        if values.get("success"):
            for fault in self.repo.resolve_faults(provider, key_fingerprint, occurred_at):
                self._notify_async(fault, recovery=True)
            return

        category = str(values.get("error_category") or SearchErrorCategory.OTHER.value)
        if category not in _IMMEDIATE_FAULTS and category not in _TRANSIENT_FAULTS:
            return
        fault, activated = self.repo.record_fault_event(
            provider=provider,
            key_fingerprint=key_fingerprint,
            category=category,
            occurred_at=occurred_at,
            call_id=call_id,
            error_summary=values.get("error_summary"),
            immediate=category in _IMMEDIATE_FAULTS,
            transient_window=timedelta(minutes=10),
            threshold=3,
        )
        if activated:
            self._notify_async(fault, recovery=False)

    def dashboard(
        self,
        *,
        from_dt: datetime,
        to_dt: datetime,
        provider: Optional[str] = None,
        call_source: Optional[str] = None,
        success: Optional[bool] = None,
        error_category: Optional[str] = None,
        key_fingerprint: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        filters = {
            "from_dt": from_dt,
            "to_dt": to_dt,
            "provider": provider,
            "call_source": call_source,
            "success": success,
            "error_category": error_category,
            "key_fingerprint": key_fingerprint,
        }
        self.reconcile_configured_keys()
        return {
            "audit_started_at": self._iso(self.repo.audit_started_at()),
            "summary": self.repo.summary(**filters),
            "by_provider": self.repo.breakdown("provider", **filters),
            "by_key": self.repo.breakdown("key_fingerprint", **filters),
            "by_source": self.repo.breakdown("call_source", **filters),
            "calls": self._serialize_page(
                self.repo.list_calls(page=max(1, page), page_size=max(1, min(page_size, 200)), **filters)
            ),
            "faults": self.fault_status(reconcile=False),
            "audit_health": self.audit_health(),
        }

    def fault_status(self, *, reconcile: bool = True) -> Dict[str, Any]:
        if reconcile:
            self.reconcile_configured_keys()
        active = [self._serialize_datetimes(item) for item in self.repo.list_active_faults()]
        configured = self.configured_provider_fingerprints()
        by_provider: List[Dict[str, Any]] = []
        providers = sorted(set(configured) | {item["provider"] for item in active})
        for provider in providers:
            keys = set(configured.get(provider, ()))
            failed = {item["key_fingerprint"] for item in active if item["provider"] == provider}
            if not failed:
                status = "normal"
            elif keys and keys.issubset(failed):
                status = "unavailable"
            else:
                status = "degraded"
            by_provider.append(
                {
                    "provider": provider,
                    "status": status,
                    "configured_keys": len(keys),
                    "failed_keys": len(failed),
                }
            )
        return {
            "active_faults": active,
            "providers": by_provider,
            "audit_health": self.audit_health(),
        }

    def get_call_detail(self, call_id: int) -> Optional[Dict[str, Any]]:
        row = self.repo.get_call(call_id)
        if row is None:
            return None
        result = self._serialize_datetimes(row)
        for key in ("request_snapshot_json", "response_snapshot_json"):
            try:
                result[key.removesuffix("_json")] = json.loads(result.pop(key))
            except (TypeError, ValueError):
                result[key.removesuffix("_json")] = result.pop(key)
        return result

    def iter_csv(self, **filters: Any) -> Iterator[str]:
        columns = [
            "id", "requested_at", "completed_at", "provider", "key_fingerprint",
            "call_source", "operation", "stock_code", "stock_name", "dimension",
            "lookback_days", "business_search_id", "logical_request_id", "provider_attempt",
            "physical_attempt", "http_method", "endpoint", "success", "http_status",
            "provider_code", "provider_request_id", "duration_ms", "result_count",
            "error_category", "error_summary", "request_truncated", "request_size_bytes",
            "request_sha256", "response_truncated", "response_size_bytes", "response_sha256",
        ]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        yield "\ufeff" + output.getvalue()
        output.seek(0)
        output.truncate(0)
        for row in self.repo.iter_calls(**filters):
            writer.writerow(self._serialize_datetimes(row))
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    def configured_provider_fingerprints(self) -> Dict[str, Sequence[str]]:
        try:
            config = get_config()
        except Exception as exc:
            logger.warning("[Search audit] 无法读取搜索供应商配置: %s", sanitize_diagnostic_text(exc))
            return {}
        result: Dict[str, Sequence[str]] = {}
        for provider, field in _PROVIDER_CONFIG_FIELDS.items():
            values = list(getattr(config, field, None) or [])
            if values:
                result[provider] = [fingerprint_search_value(value, domain="search_api_key") for value in values]
        return result

    def reconcile_configured_keys(self) -> None:
        configured = self.configured_provider_fingerprints()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            resolved = self.repo.resolve_removed_keys(configured, now)
        except Exception as exc:
            logger.warning("[Search audit] Key 配置对账失败: %s", sanitize_diagnostic_text(exc))
            return
        for fault in resolved:
            self._notify_async(fault, recovery=True)

    def audit_health(self) -> Dict[str, Any]:
        persisted = self.repo.audit_gap_totals()
        with _GAP_LOCK:
            process_count = _GAP_COUNT
            process_last = _GAP_LAST_AT
        persisted_count = int(persisted.get("persisted_lost_count") or 0)
        return {
            "healthy": process_count == 0 and persisted_count == 0,
            "process_lost_count": process_count,
            "persisted_lost_count": persisted_count,
            "last_gap_at": self._iso(process_last or persisted.get("last_gap_at")),
        }

    @staticmethod
    def _remember_gap(exc: Exception) -> None:
        global _GAP_COUNT, _GAP_FIRST_AT, _GAP_LAST_AT, _GAP_LAST_ERROR
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with _GAP_LOCK:
            _GAP_COUNT += 1
            _GAP_FIRST_AT = _GAP_FIRST_AT or now
            _GAP_LAST_AT = now
            _GAP_LAST_ERROR = sanitize_diagnostic_text(exc)

    def _flush_remembered_gap(self) -> None:
        global _GAP_COUNT, _GAP_FIRST_AT, _GAP_LAST_AT, _GAP_LAST_ERROR
        with _GAP_LOCK:
            if not _GAP_COUNT or _GAP_FIRST_AT is None or _GAP_LAST_AT is None:
                return
            values = (_GAP_COUNT, _GAP_FIRST_AT, _GAP_LAST_AT, _GAP_LAST_ERROR)
        try:
            self.repo.insert_gap(
                lost_count=values[0],
                first_failed_at=values[1],
                last_failed_at=values[2],
                error_summary=values[3],
            )
        except Exception:
            return
        with _GAP_LOCK:
            _GAP_COUNT = 0
            _GAP_FIRST_AT = None
            _GAP_LAST_AT = None
            _GAP_LAST_ERROR = None

    def _notify_async(self, fault: Dict[str, Any], *, recovery: bool) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if not self.repo.claim_notification(
            int(fault["id"]),
            recovery=recovery,
            now=now,
            cooldown=timedelta(hours=24),
        ):
            return
        threading.Thread(
            target=self._send_notification,
            args=(dict(fault), recovery),
            name="search-provider-fault-notification",
            daemon=True,
        ).start()

    def _send_notification(self, fault: Dict[str, Any], recovery: bool) -> None:
        status = "failed"
        try:
            from src.notification import NotificationService

            provider = fault["provider"]
            category = fault["error_category"]
            key_short = str(fault["key_fingerprint"])[:8]
            state = "已恢复" if recovery else "发生持续故障"
            content = (
                f"## 搜索供应商{state}\n\n"
                f"- 供应商：{provider}\n"
                f"- Key 指纹：{key_short}\n"
                f"- 类别：{category}\n"
                f"- 时间：{datetime.now(_CST).strftime('%Y-%m-%d %H:%M:%S')}\n"
                "- 查看：Web 用量分析 → 搜索调用\n"
            )
            result = NotificationService().send_with_results(
                content,
                route_type="alert",
                severity="warning" if recovery else "critical",
                dedup_key=f"search:{provider}:{key_short}:{category}:{'recovered' if recovery else 'active'}",
                cooldown_key=f"search:{provider}:{key_short}:{category}",
            )
            status = result.status
        except Exception as exc:
            status = "exception"
            logger.warning("[Search audit] 故障通知发送失败: %s", sanitize_diagnostic_text(exc))
        finally:
            try:
                self.repo.update_notification_status(int(fault["id"]), status)
            except Exception:
                logger.warning("[Search audit] 故障通知状态回写失败", exc_info=True)

    @classmethod
    def _serialize_page(cls, page: Dict[str, Any]) -> Dict[str, Any]:
        return {**page, "items": [cls._serialize_datetimes(item) for item in page["items"]]}

    @classmethod
    def _serialize_datetimes(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: cls._serialize_datetimes(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._serialize_datetimes(item) for item in value]
        if isinstance(value, datetime):
            return cls._iso(value)
        return value

    @staticmethod
    def _iso(value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        utc = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return utc.astimezone(_CST).isoformat()
