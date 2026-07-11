# -*- coding: utf-8 -*-
"""Unit tests for task queue MAX_WORKERS runtime synchronization."""

from __future__ import annotations

import sys
import types
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

# Keep task_queue import lightweight in environments without optional deps,
# but restore sys.modules immediately to avoid cross-test pollution.
_orig_data_provider_base = sys.modules.get("data_provider.base")
_orig_data_provider = sys.modules.get("data_provider")
_using_data_provider_stub = False

if _orig_data_provider_base is None:
    try:
        __import__("data_provider.base")
    except Exception:
        base_mod = types.ModuleType("data_provider.base")
        base_mod.canonical_stock_code = lambda x: (x or "").strip().upper()
        base_mod.normalize_stock_code = lambda x: (x or "").strip().upper().removesuffix(".SH").removesuffix(".SZ")
        base_mod.is_bse_code = lambda x: False
        sys.modules["data_provider.base"] = base_mod
        _using_data_provider_stub = True

if _using_data_provider_stub and _orig_data_provider is None:
    pkg_mod = types.ModuleType("data_provider")
    pkg_mod.base = sys.modules["data_provider.base"]
    sys.modules["data_provider"] = pkg_mod

from src.services.task_queue import AnalysisTaskQueue, TaskInfo, TaskStatus, get_task_queue, _dedupe_stock_code_key

if _using_data_provider_stub:
    if _orig_data_provider_base is None:
        sys.modules.pop("data_provider.base", None)
    else:
        sys.modules["data_provider.base"] = _orig_data_provider_base

    if _orig_data_provider is None:
        sys.modules.pop("data_provider", None)
    else:
        sys.modules["data_provider"] = _orig_data_provider


class TaskQueueConfigSyncTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._original_instance = AnalysisTaskQueue._instance
        AnalysisTaskQueue._instance = None

    def tearDown(self) -> None:
        queue = AnalysisTaskQueue._instance
        if queue is not None and queue is not self._original_instance:
            executor = getattr(queue, "_executor", None)
            if executor is not None and hasattr(executor, "shutdown"):
                executor.shutdown(wait=False)
        AnalysisTaskQueue._instance = self._original_instance

    def test_sync_max_workers_applies_when_idle(self) -> None:
        queue = AnalysisTaskQueue(max_workers=3)
        shutdown_wait_args = []

        class ExecutorStub:
            def shutdown(self, wait=True, cancel_futures=False):
                shutdown_wait_args.append(wait)

        queue._executor = ExecutorStub()

        result = queue.sync_max_workers(1)
        self.assertEqual(result, "applied")
        self.assertEqual(queue.max_workers, 1)
        self.assertIsNone(queue._executor)
        self.assertEqual(shutdown_wait_args, [False])

    def test_sync_max_workers_deferred_when_busy(self) -> None:
        queue = AnalysisTaskQueue(max_workers=3)
        queue._analyzing_stocks["600519"] = "task1"

        result = queue.sync_max_workers(1)
        self.assertEqual(result, "deferred_busy")
        self.assertEqual(queue.max_workers, 3)

    def test_get_task_queue_uses_runtime_configured_max_workers(self) -> None:
        with patch("src.config.get_config", return_value=SimpleNamespace(max_workers=1)):
            queue = get_task_queue()

        self.assertEqual(queue.max_workers, 1)

    def test_get_task_queue_keeps_singleton_identity_after_sync(self) -> None:
        with patch("src.config.get_config", return_value=SimpleNamespace(max_workers=3)):
            first = get_task_queue()
        with patch("src.config.get_config", return_value=SimpleNamespace(max_workers=1)):
            second = get_task_queue()

        self.assertIs(first, second)
        self.assertEqual(second.max_workers, 1)

    def test_get_task_queue_supports_string_max_workers(self) -> None:
        with patch("src.config.get_config", return_value=SimpleNamespace(max_workers="2")):
            queue = get_task_queue()

        self.assertEqual(queue.max_workers, 2)

    def test_dedupe_stock_code_key_normalizes_market_suffix(self) -> None:
        self.assertEqual(_dedupe_stock_code_key(" 600519.sh "), "600519")

    def test_get_task_queue_defers_sync_when_busy(self) -> None:
        queue = AnalysisTaskQueue(max_workers=3)
        queue._analyzing_stocks["600519"] = "task1"

        with patch("src.config.get_config", return_value=SimpleNamespace(max_workers=1)):
            synced = get_task_queue()

        self.assertIs(synced, queue)
        self.assertEqual(synced.max_workers, 3)

    def test_processing_task_times_out_and_releases_dedupe_lock(self) -> None:
        queue = AnalysisTaskQueue(max_workers=1)
        queue.sync_task_timeout_seconds(5)
        task = TaskInfo(
            task_id="task-timeout",
            stock_code="600519",
            status=TaskStatus.PROCESSING,
            started_at=datetime.now() - timedelta(seconds=6),
            message="正在分析中...",
        )
        queue._tasks[task.task_id] = task
        queue._analyzing_stocks[_dedupe_stock_code_key(task.stock_code)] = task.task_id

        snapshot = queue.get_task(task.task_id)

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.status, TaskStatus.FAILED)
        self.assertIn("超时", snapshot.error)
        self.assertFalse(queue.is_analyzing("600519.SH"))

    def test_submit_broadcasts_expired_task_failure(self) -> None:
        queue = AnalysisTaskQueue(max_workers=1)
        queue.sync_task_timeout_seconds(5)
        task = TaskInfo(
            task_id="task-timeout",
            stock_code="600519",
            status=TaskStatus.PROCESSING,
            started_at=datetime.now() - timedelta(seconds=6),
            message="正在分析中...",
        )
        queue._tasks[task.task_id] = task
        queue._analyzing_stocks[_dedupe_stock_code_key(task.stock_code)] = task.task_id

        events = []
        queue._broadcast_event = lambda event_type, data: events.append((event_type, data))
        queue.executor.submit = lambda *args, **kwargs: SimpleNamespace(cancel=lambda: None)

        queue.submit_task("000001")

        self.assertIn(("task_failed", queue.get_task("task-timeout").to_dict()), events)

    def test_late_task_completion_does_not_overwrite_timeout_or_new_lock(self) -> None:
        queue = AnalysisTaskQueue(max_workers=1)
        old_task = TaskInfo(
            task_id="old-task",
            stock_code="600519",
            status=TaskStatus.FAILED,
            started_at=datetime.now() - timedelta(seconds=60),
            completed_at=datetime.now(),
            error="任务执行超过 5s，已标记失败",
        )
        new_task = TaskInfo(
            task_id="new-task",
            stock_code="600519",
            status=TaskStatus.PROCESSING,
            started_at=datetime.now(),
        )
        dedupe_key = _dedupe_stock_code_key("600519")
        queue._tasks[old_task.task_id] = old_task
        queue._tasks[new_task.task_id] = new_task
        queue._analyzing_stocks[dedupe_key] = new_task.task_id

        applied = queue._mark_task_completed_if_active("old-task", {"stock_name": "贵州茅台"})

        self.assertFalse(applied)
        self.assertEqual(queue.get_task("old-task").status, TaskStatus.FAILED)
        self.assertEqual(queue.get_analyzing_task_id("600519"), "new-task")

    def test_get_task_queue_syncs_analysis_task_timeout(self) -> None:
        with patch(
            "src.config.get_config",
            return_value=SimpleNamespace(max_workers=1, analysis_task_timeout_seconds=7),
        ):
            queue = get_task_queue()

        self.assertEqual(queue.analysis_task_timeout_seconds, 7)


if __name__ == "__main__":
    unittest.main()
