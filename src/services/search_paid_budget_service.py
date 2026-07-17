# -*- coding: utf-8 -*-
"""Persistent paid-search request budget protection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import threading
from typing import Any, Callable, Dict, Optional

from src.config import get_config
from src.repositories.search_usage_repo import SearchUsageRepository
from src.utils.sanitize import sanitize_diagnostic_text


logger = logging.getLogger(__name__)
_CST = timezone(timedelta(hours=8))


class SearchBudgetExceeded(RuntimeError):
    """Raised before a paid request when the daily hard limit is exhausted."""


class SearchBudgetUnavailable(RuntimeError):
    """Raised before a paid request when a safe reservation cannot be persisted."""


class SearchPaidBudgetService:
    """Reserve paid-provider calls across threads, processes, and restarts."""

    def __init__(
        self,
        repo: Optional[SearchUsageRepository] = None,
        config_getter: Callable[[], Any] = get_config,
    ):
        self.repo = repo
        self._config_getter = config_getter

    def reserve_before_request(self, provider: str) -> Optional[Dict[str, Any]]:
        if str(provider or "").strip().lower() != "anspire":
            return None

        try:
            config = self._config_getter()
        except Exception as exc:
            logger.error(
                "[Search budget] 无法读取预算配置，已阻断 Anspire 付费请求: %s",
                sanitize_diagnostic_text(exc),
            )
            raise SearchBudgetUnavailable("budget_unavailable: 无法读取 Anspire 每日预算配置") from exc
        if str(getattr(config, "search_routing_mode", "legacy") or "legacy").lower() != "searxng_first_cn":
            return None

        warning_limit = max(0, int(getattr(config, "anspire_daily_warning_requests", 30) or 0))
        hard_limit = max(0, int(getattr(config, "anspire_daily_hard_limit_requests", 50) or 0))
        if warning_limit == 0 and hard_limit == 0:
            return None

        now_cst = datetime.now(_CST)
        reserved_at = now_cst.astimezone(timezone.utc).replace(tzinfo=None)
        try:
            repo = self.repo or SearchUsageRepository()
            reservation = repo.reserve_paid_request(
                provider="Anspire",
                budget_date=now_cst.date(),
                warning_limit=warning_limit,
                hard_limit=hard_limit,
                reserved_at=reserved_at,
            )
        except Exception as exc:
            logger.error(
                "[Search budget] Anspire 预算预留失败，已阻断付费请求: %s",
                sanitize_diagnostic_text(exc),
                exc_info=True,
            )
            raise SearchBudgetUnavailable("budget_unavailable: 无法可靠预留 Anspire 每日预算") from exc

        reserved = int(reservation.get("reserved_requests") or 0)
        if reservation.get("warning_claimed"):
            self._notify_async(reserved=reserved, limit=warning_limit, hard=False)
        if reservation.get("hard_limit_claimed"):
            self._notify_async(reserved=reserved, limit=hard_limit, hard=True)
        if not reservation.get("allowed"):
            raise SearchBudgetExceeded(
                f"budget_blocked: Anspire 当日已预留 {reserved} 次，硬上限为 {hard_limit} 次"
            )
        return reservation

    @staticmethod
    def _notify_async(*, reserved: int, limit: int, hard: bool) -> None:
        threading.Thread(
            target=SearchPaidBudgetService._send_notification,
            kwargs={"reserved": reserved, "limit": limit, "hard": hard},
            name="search-paid-budget-notification",
            daemon=True,
        ).start()

    @staticmethod
    def _send_notification(*, reserved: int, limit: int, hard: bool) -> None:
        try:
            from src.notification import NotificationService

            level = "硬上限" if hard else "预警阈值"
            content = (
                f"## Anspire 搜索预算{level}\n\n"
                f"- 北京时间日期：{datetime.now(_CST).strftime('%Y-%m-%d')}\n"
                f"- 已预留请求：{reserved}\n"
                f"- 配置阈值：{limit}\n"
                f"- 状态：{'后续付费请求将被阻断' if hard else '请检查 SearXNG 可用性与 fallback 比例'}\n"
            )
            NotificationService().send_with_results(
                content,
                route_type="alert",
                severity="critical" if hard else "warning",
                dedup_key=f"search:Anspire:daily-budget:{datetime.now(_CST).date()}:{'hard' if hard else 'warning'}",
                cooldown_key="search:Anspire:daily-budget",
            )
        except Exception as exc:
            logger.warning("[Search budget] 预算告警发送失败: %s", sanitize_diagnostic_text(exc))
