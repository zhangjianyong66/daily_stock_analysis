# -*- coding: utf-8 -*-
"""Recoverable in-process tasks for portfolio screenshot recognition."""

from __future__ import annotations

import copy
import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from src.services.portfolio_screenshot_import_service import (
    ImageInput,
    PortfolioImageBatchTimeoutError,
    PortfolioImageProcessingCancelled,
    PortfolioScreenshotImportService,
)

logger = logging.getLogger(__name__)

PortfolioImageMode = Literal["positions", "trades"]
PORTFOLIO_IMAGE_TASK_DEADLINE_SECONDS = 60 * 60


class PortfolioImageTaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    REVIEW_REQUIRED = "review_required"
    COMMITTING = "committing"
    FAILED = "failed"


BLOCKING_STATUSES = frozenset(
    {
        PortfolioImageTaskStatus.PENDING,
        PortfolioImageTaskStatus.PROCESSING,
        PortfolioImageTaskStatus.CANCEL_REQUESTED,
        PortfolioImageTaskStatus.REVIEW_REQUIRED,
        PortfolioImageTaskStatus.COMMITTING,
    }
)


class PortfolioImageTaskError(Exception):
    """Base task error with a stable API code."""

    code = "portfolio_image_task_state_conflict"


class PortfolioImageTaskActiveError(PortfolioImageTaskError):
    code = "portfolio_image_task_active"

    def __init__(self, task_id: str, status: str) -> None:
        self.existing_task_id = task_id
        self.existing_status = status
        super().__init__("已有图片识别任务，请继续处理当前任务")


class PortfolioImageTaskNotFoundError(PortfolioImageTaskError):
    code = "portfolio_image_task_not_found"


class PortfolioImageTaskStateConflictError(PortfolioImageTaskError):
    code = "portfolio_image_task_state_conflict"


class PortfolioImageDraftConflictError(PortfolioImageTaskError):
    code = "portfolio_image_draft_conflict"

    def __init__(self, current_revision: int) -> None:
        self.current_revision = current_revision
        super().__init__("校对草稿已被其他页面更新，请重新加载最新版本")


@dataclass
class PortfolioImageTaskFile:
    index: int
    filename: Optional[str]
    status: str = "pending"
    record_count: int = 0
    error: Optional[str] = None
    removed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "filename": self.filename,
            "status": self.status,
            "record_count": self.record_count,
            "error": self.error,
            "removed": self.removed,
        }


@dataclass
class PortfolioImageTask:
    task_id: str
    trace_id: str
    mode: PortfolioImageMode
    account_id: int
    account_name: str
    date_value: date
    status: PortfolioImageTaskStatus = PortfolioImageTaskStatus.PENDING
    message: str = "图片识别任务已创建"
    error_code: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    deadline_monotonic: float = field(
        default_factory=lambda: time.monotonic() + PORTFOLIO_IMAGE_TASK_DEADLINE_SECONDS
    )
    files: List[PortfolioImageTaskFile] = field(default_factory=list)
    current_file_index: Optional[int] = None
    current_attempt: Optional[int] = None
    max_attempts: int = 2
    success_count: int = 0
    failure_count: int = 0
    batch_id: Optional[str] = None
    draft: Optional[Dict[str, Any]] = None
    draft_revision: Optional[int] = None
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    future: Optional[Future] = field(default=None, repr=False)
    compatibility_sync: bool = False

    def to_snapshot(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "mode": self.mode,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "status": self.status.value,
            "message": self.message,
            "error_code": self.error_code,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "files": [item.to_dict() for item in self.files],
            "current_file_index": self.current_file_index,
            "total_files": len(self.files),
            "current_attempt": self.current_attempt,
            "max_attempts": self.max_attempts,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "batch_id": self.batch_id,
            "draft_revision": self.draft_revision,
            "draft": copy.deepcopy(self.draft),
        }
        if self.mode == "positions":
            payload["snapshot_date"] = self.date_value.isoformat()
            payload["default_trade_date"] = None
        else:
            payload["snapshot_date"] = None
            payload["default_trade_date"] = self.date_value.isoformat()
        return payload

    def to_summary(self, *, status: Optional[str] = None) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "mode": self.mode,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "status": status or self.status.value,
            "message": self.message,
            "current_file_index": self.current_file_index,
            "total_files": len(self.files),
            "current_attempt": self.current_attempt,
            "max_attempts": self.max_attempts,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "draft_revision": self.draft_revision,
        }


class PortfolioImageTaskManager:
    """Thread-safe singleton owning the global portfolio-image task slot."""

    _instance: Optional["PortfolioImageTaskManager"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> "PortfolioImageTaskManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._lock = threading.RLock()
        self._executor: Optional[ThreadPoolExecutor] = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="portfolio_image_task_",
        )
        self._current: Optional[PortfolioImageTask] = None
        self._closed = False
        self._initialized = True

    @classmethod
    def reset_instance(cls) -> None:
        with cls._instance_lock:
            instance = cls._instance
            cls._instance = None
        if instance is not None:
            instance.shutdown(wait=False)

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            executor = self._executor
            self._executor = None
            self._closed = True
            current = self._current
            if current is not None:
                current.cancel_event.set()
        if executor is not None:
            executor.shutdown(wait=wait, cancel_futures=True)

    def submit_task(
        self,
        *,
        mode: PortfolioImageMode,
        account_id: int,
        date_value: date,
        images: List[ImageInput],
        service: Optional[PortfolioScreenshotImportService] = None,
        deadline_seconds: float = PORTFOLIO_IMAGE_TASK_DEADLINE_SECONDS,
    ) -> Dict[str, Any]:
        screenshot_service = service or PortfolioScreenshotImportService()
        with self._lock:
            self._assert_slot_available_locked()
        account = self._validate_request(
            screenshot_service,
            mode=mode,
            account_id=account_id,
            date_value=date_value,
            images=images,
        )
        task = self._new_task(
            mode=mode,
            account_id=account_id,
            account_name=str(getattr(account, "name", None) or f"#{account_id}"),
            date_value=date_value,
            images=images,
            deadline_seconds=deadline_seconds,
        )
        with self._lock:
            self._assert_slot_available_locked()
            self._current = task
            try:
                executor = self._executor
                if executor is None:
                    raise RuntimeError("Portfolio image task manager is shut down")
                task.future = executor.submit(
                    self._execute_async_task,
                    task.task_id,
                    list(images),
                    screenshot_service,
                )
            except Exception:
                self._current = None
                raise
            snapshot = task.to_snapshot()
        self._publish(task)
        return snapshot

    def run_sync_parse(
        self,
        *,
        mode: PortfolioImageMode,
        account_id: int,
        date_value: date,
        images: List[ImageInput],
        service: Optional[PortfolioScreenshotImportService] = None,
        deadline_seconds: float = PORTFOLIO_IMAGE_TASK_DEADLINE_SECONDS,
    ) -> Dict[str, Any]:
        screenshot_service = service or PortfolioScreenshotImportService()
        task = self._new_task(
            mode=mode,
            account_id=account_id,
            account_name=f"#{account_id}",
            date_value=date_value,
            images=images,
            deadline_seconds=deadline_seconds,
            compatibility_sync=True,
        )
        with self._lock:
            self._assert_slot_available_locked()
            self._current = task
            task.status = PortfolioImageTaskStatus.PROCESSING
            task.started_at = datetime.now()
            task.message = "正在识别图片"
        self._publish(task)
        terminal_status = "completed"
        try:
            return self._parse(task.task_id, list(images), screenshot_service)
        except PortfolioImageProcessingCancelled as exc:
            terminal_status = "cancelled"
            raise PortfolioImageTaskStateConflictError("同步识别已取消") from exc
        except PortfolioImageBatchTimeoutError as exc:
            terminal_status = "failed"
            raise PortfolioImageTaskStateConflictError("同步识别超过整体运行上限") from exc
        except Exception:
            terminal_status = "failed"
            raise
        finally:
            with self._lock:
                current = self._current
                if current is not None and current.task_id == task.task_id:
                    current.finished_at = datetime.now()
                    summary = current.to_summary(status=terminal_status)
                    self._current = None
                else:
                    summary = task.to_summary(status=terminal_status)
            self._publish_summary(summary)

    def get_current_task(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._current.to_snapshot() if self._current is not None else None

    def get_task(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            task = self._require_current_locked(task_id)
            return task.to_snapshot()

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        publish_snapshot: Optional[Dict[str, Any]] = None
        with self._lock:
            task = self._require_current_locked(task_id)
            if task.status == PortfolioImageTaskStatus.PENDING:
                task.cancel_event.set()
                if task.future is not None and task.future.cancel():
                    task.status = PortfolioImageTaskStatus.CANCELLED
                    task.message = "图片识别任务已取消"
                    task.finished_at = datetime.now()
                else:
                    task.status = PortfolioImageTaskStatus.CANCEL_REQUESTED
                    task.message = "正在等待当前识别调用结束后取消"
                publish_snapshot = task.to_snapshot()
            elif task.status == PortfolioImageTaskStatus.PROCESSING:
                task.cancel_event.set()
                task.status = PortfolioImageTaskStatus.CANCEL_REQUESTED
                task.message = "正在等待当前识别调用结束后取消"
                publish_snapshot = task.to_snapshot()
            elif task.status == PortfolioImageTaskStatus.CANCEL_REQUESTED:
                publish_snapshot = task.to_snapshot()
            else:
                raise PortfolioImageTaskStateConflictError(f"当前状态不支持取消: {task.status.value}")
        self._publish_summary(self._summary_from_snapshot(publish_snapshot))
        return publish_snapshot

    def discard_task(self, task_id: str) -> None:
        with self._lock:
            task = self._require_current_locked(task_id)
            if task.status not in {
                PortfolioImageTaskStatus.REVIEW_REQUIRED,
                PortfolioImageTaskStatus.FAILED,
                PortfolioImageTaskStatus.CANCELLED,
            }:
                raise PortfolioImageTaskStateConflictError(f"当前状态不支持放弃或清除: {task.status.value}")
            summary = task.to_summary(status="discarded")
            task.draft = None
            self._current = None
        self._publish_summary(summary)

    def update_draft(
        self,
        task_id: str,
        *,
        expected_revision: int,
        files: List[Dict[str, Any]],
        positions: Optional[List[Dict[str, Any]]] = None,
        trades: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            task = self._require_current_locked(task_id)
            if task.status != PortfolioImageTaskStatus.REVIEW_REQUIRED or task.draft is None:
                raise PortfolioImageTaskStateConflictError("当前任务没有可更新的校对草稿")
            if task.draft_revision != expected_revision:
                raise PortfolioImageDraftConflictError(task.draft_revision or 0)

            server_files = {int(item["index"]): item for item in task.draft.get("files", [])}
            requested_files = {int(item["index"]): item for item in files}
            if set(server_files) != set(requested_files):
                raise PortfolioImageTaskStateConflictError("草稿文件列表与当前任务不一致")
            for index, server_file in server_files.items():
                server_file["removed"] = bool(requested_files[index].get("removed", False))
                task.files[index].removed = server_file["removed"]

            if task.mode == "positions":
                if positions is None or trades is not None:
                    raise PortfolioImageTaskStateConflictError("持仓任务草稿类型不匹配")
                task.draft["positions"] = copy.deepcopy(positions)
            else:
                if trades is None or positions is not None:
                    raise PortfolioImageTaskStateConflictError("成交任务草稿类型不匹配")
                task.draft["trades"] = copy.deepcopy(trades)

            task.draft_revision = expected_revision + 1
            snapshot = task.to_snapshot()
        self._publish_summary(self._summary_from_snapshot(snapshot))
        return snapshot

    def begin_commit(
        self,
        task_id: str,
        *,
        mode: PortfolioImageMode,
        account_id: int,
        batch_id: str,
        expected_revision: Optional[int],
        date_value: Optional[date] = None,
    ) -> None:
        with self._lock:
            task = self._require_current_locked(task_id)
            if task.status != PortfolioImageTaskStatus.REVIEW_REQUIRED:
                raise PortfolioImageTaskStateConflictError(f"当前状态不能提交: {task.status.value}")
            if expected_revision is None or task.draft_revision != expected_revision:
                raise PortfolioImageDraftConflictError(task.draft_revision or 0)
            if task.mode != mode or task.account_id != account_id or task.batch_id != batch_id:
                raise PortfolioImageTaskStateConflictError("提交请求与当前图片任务不匹配")
            if date_value is not None and task.date_value != date_value:
                raise PortfolioImageTaskStateConflictError("提交日期与当前图片任务不匹配")
            if any(item.status == "failed" and not item.removed for item in task.files):
                raise PortfolioImageTaskStateConflictError("请先移除识别失败的图片再确认导入")
            task.status = PortfolioImageTaskStatus.COMMITTING
            task.message = "正在写入持仓账本"
            snapshot = task.to_snapshot()
        self._publish_summary(self._summary_from_snapshot(snapshot))

    def finish_commit(self, task_id: str) -> None:
        with self._lock:
            task = self._require_current_locked(task_id)
            if task.status != PortfolioImageTaskStatus.COMMITTING:
                raise PortfolioImageTaskStateConflictError("图片任务不在提交状态")
            task.message = "图片识别结果已确认导入"
            summary = task.to_summary(status="committed")
            task.draft = None
            self._current = None
        self._publish_summary(summary)

    def rollback_commit(self, task_id: str) -> None:
        with self._lock:
            task = self._current
            if task is None or task.task_id != task_id or task.status != PortfolioImageTaskStatus.COMMITTING:
                return
            task.status = PortfolioImageTaskStatus.REVIEW_REQUIRED
            task.message = "导入失败，校对草稿已保留"
            snapshot = task.to_snapshot()
        self._publish_summary(self._summary_from_snapshot(snapshot))

    def ensure_legacy_commit_allowed(self) -> None:
        with self._lock:
            if self._current is not None and self._current.status in BLOCKING_STATUSES:
                raise PortfolioImageTaskActiveError(self._current.task_id, self._current.status.value)

    def _execute_async_task(
        self,
        task_id: str,
        images: List[ImageInput],
        service: PortfolioScreenshotImportService,
    ) -> None:
        try:
            with self._lock:
                task = self._require_current_locked(task_id)
                if task.cancel_event.is_set():
                    task.status = PortfolioImageTaskStatus.CANCELLED
                    task.message = "图片识别任务已取消"
                    task.finished_at = datetime.now()
                    snapshot = task.to_snapshot()
                    should_run = False
                else:
                    task.status = PortfolioImageTaskStatus.PROCESSING
                    task.started_at = datetime.now()
                    task.message = "正在识别图片"
                    snapshot = task.to_snapshot()
                    should_run = True
            self._publish_summary(self._summary_from_snapshot(snapshot))
            if not should_run:
                return

            result = self._parse(task_id, images, service)
            with self._lock:
                task = self._require_current_locked(task_id)
                if task.cancel_event.is_set() or task.status == PortfolioImageTaskStatus.CANCEL_REQUESTED:
                    raise PortfolioImageProcessingCancelled()
                if time.monotonic() >= task.deadline_monotonic:
                    raise PortfolioImageBatchTimeoutError()
                for file_result in result.get("files", []):
                    index = int(file_result.get("index", -1))
                    if not 0 <= index < len(task.files):
                        continue
                    task_file = task.files[index]
                    task_file.status = str(file_result.get("status") or "failed")
                    task_file.record_count = int(file_result.get("record_count") or 0)
                    task_file.error = file_result.get("error")
                task.success_count = sum(1 for item in task.files if item.status == "success")
                task.failure_count = sum(1 for item in task.files if item.status == "failed")
                successful_files = [item for item in result.get("files", []) if item.get("status") == "success"]
                if not successful_files:
                    task.status = PortfolioImageTaskStatus.FAILED
                    task.error_code = self._first_file_error(result) or "vision_failed"
                    task.message = "所有图片识别均失败，请检查图片或 Vision 配置后重试"
                    task.finished_at = datetime.now()
                else:
                    draft = copy.deepcopy(result)
                    for item in draft.get("files", []):
                        item["removed"] = False
                    task.status = PortfolioImageTaskStatus.REVIEW_REQUIRED
                    task.batch_id = str(result.get("batch_id") or "")
                    task.draft = draft
                    task.draft_revision = 1
                    task.message = "识别完成，请校对后确认导入"
                    task.finished_at = datetime.now()
                snapshot = task.to_snapshot()
            self._publish_summary(self._summary_from_snapshot(snapshot))
        except PortfolioImageProcessingCancelled:
            self._mark_cancelled(task_id)
        except PortfolioImageBatchTimeoutError:
            self._mark_failed(task_id, "portfolio_image_task_timeout", "图片识别任务超过 60 分钟运行上限")
        except PortfolioImageTaskNotFoundError:
            logger.debug("图片任务已被清除，忽略迟到结果: task_id=%s", task_id)
        except Exception as exc:  # pragma: no cover - guarded by focused manager tests
            logger.error("图片识别任务失败: task_id=%s error=%s", task_id, type(exc).__name__, exc_info=True)
            self._mark_failed(task_id, getattr(exc, "code", "vision_failed"), "图片识别任务失败，请稍后重试")
        finally:
            images.clear()

    def _parse(
        self,
        task_id: str,
        images: List[ImageInput],
        service: PortfolioScreenshotImportService,
    ) -> Dict[str, Any]:
        with self._lock:
            task = self._require_current_locked(task_id)
            mode = task.mode
            account_id = task.account_id
            date_value = task.date_value
            deadline = task.deadline_monotonic

        kwargs = {
            "account_id": account_id,
            "images": images,
            "progress_callback": lambda event: self._handle_progress(task_id, event),
            "cancel_requested": lambda: self._is_cancel_requested(task_id),
            "deadline_monotonic": deadline,
        }
        if mode == "positions":
            return service.parse_position_images(snapshot_date=date_value, **kwargs)
        return service.parse_trade_images(default_trade_date=date_value, **kwargs)

    def _handle_progress(self, task_id: str, event: Dict[str, Any]) -> None:
        with self._lock:
            task = self._require_current_locked(task_id)
            if task.cancel_event.is_set() or task.status == PortfolioImageTaskStatus.CANCEL_REQUESTED:
                raise PortfolioImageProcessingCancelled()
            if time.monotonic() >= task.deadline_monotonic:
                raise PortfolioImageBatchTimeoutError()

            file_index = int(event.get("file_index", 0))
            if not 0 <= file_index < len(task.files):
                return
            phase = event.get("phase")
            task.current_file_index = file_index + 1
            if phase == "file_started":
                task.files[file_index].status = "processing"
                task.current_attempt = None
                task.message = f"正在识别第 {file_index + 1}/{len(task.files)} 张图片"
            elif phase == "attempt":
                task.current_attempt = int(event.get("attempt") or 1)
                task.max_attempts = int(event.get("max_attempts") or task.max_attempts)
                task.message = (
                    f"正在识别第 {file_index + 1}/{len(task.files)} 张图片，"
                    f"尝试 {task.current_attempt}/{task.max_attempts}"
                )
            elif phase == "file_completed":
                item = task.files[file_index]
                item.status = str(event.get("status") or "failed")
                item.record_count = int(event.get("record_count") or 0)
                item.error = event.get("error")
                task.success_count = sum(1 for file in task.files if file.status == "success")
                task.failure_count = sum(1 for file in task.files if file.status == "failed")
            summary = task.to_summary()
        self._publish_summary(summary)

    def _is_cancel_requested(self, task_id: str) -> bool:
        with self._lock:
            task = self._current
            return bool(
                task is None
                or task.task_id != task_id
                or task.cancel_event.is_set()
                or task.status == PortfolioImageTaskStatus.CANCEL_REQUESTED
            )

    def _mark_cancelled(self, task_id: str) -> None:
        with self._lock:
            task = self._current
            if task is None or task.task_id != task_id:
                return
            task.status = PortfolioImageTaskStatus.CANCELLED
            task.message = "图片识别任务已取消"
            task.error_code = None
            task.finished_at = datetime.now()
            task.draft = None
            snapshot = task.to_snapshot()
        self._publish_summary(self._summary_from_snapshot(snapshot))

    def _mark_failed(self, task_id: str, error_code: str, message: str) -> None:
        with self._lock:
            task = self._current
            if task is None or task.task_id != task_id:
                return
            if task.status in {PortfolioImageTaskStatus.CANCELLED, PortfolioImageTaskStatus.FAILED}:
                return
            task.status = PortfolioImageTaskStatus.FAILED
            task.error_code = error_code
            task.message = message
            task.finished_at = datetime.now()
            task.draft = None
            snapshot = task.to_snapshot()
        self._publish_summary(self._summary_from_snapshot(snapshot))

    @staticmethod
    def _validate_request(
        service: PortfolioScreenshotImportService,
        *,
        mode: PortfolioImageMode,
        account_id: int,
        date_value: date,
        images: List[ImageInput],
    ) -> Any:
        if mode == "positions":
            account = service.validate_position_images_request(
                account_id=account_id,
                snapshot_date=date_value,
                images=images,
            )
        elif mode == "trades":
            account = service.validate_trade_images_request(
                account_id=account_id,
                default_trade_date=date_value,
                images=images,
            )
        else:
            raise ValueError(f"Unsupported portfolio image mode: {mode}")
        service.validate_uploaded_images(images)
        return account

    @staticmethod
    def _new_task(
        *,
        mode: PortfolioImageMode,
        account_id: int,
        account_name: str,
        date_value: date,
        images: List[ImageInput],
        deadline_seconds: float,
        compatibility_sync: bool = False,
    ) -> PortfolioImageTask:
        task_id = uuid.uuid4().hex
        return PortfolioImageTask(
            task_id=task_id,
            trace_id=task_id,
            mode=mode,
            account_id=account_id,
            account_name=account_name,
            date_value=date_value,
            deadline_monotonic=time.monotonic() + max(0.001, float(deadline_seconds)),
            files=[
                PortfolioImageTaskFile(index=index, filename=image.filename)
                for index, image in enumerate(images)
            ],
            compatibility_sync=compatibility_sync,
        )

    def _assert_slot_available_locked(self) -> None:
        if self._current is not None and self._current.status in BLOCKING_STATUSES:
            raise PortfolioImageTaskActiveError(self._current.task_id, self._current.status.value)

    def _require_current_locked(self, task_id: str) -> PortfolioImageTask:
        if self._current is None or self._current.task_id != task_id:
            raise PortfolioImageTaskNotFoundError("图片任务不存在，可能因服务重启已中断")
        return self._current

    @staticmethod
    def _first_file_error(result: Dict[str, Any]) -> Optional[str]:
        for item in result.get("files", []):
            if item.get("error"):
                return str(item["error"])
        return None

    @staticmethod
    def _summary_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
        keys = {
            "task_id",
            "mode",
            "account_id",
            "account_name",
            "status",
            "message",
            "current_file_index",
            "total_files",
            "current_attempt",
            "max_attempts",
            "success_count",
            "failure_count",
            "draft_revision",
        }
        return {key: snapshot.get(key) for key in keys}

    def _publish(self, task: PortfolioImageTask) -> None:
        self._publish_summary(task.to_summary())

    def _publish_summary(self, summary: Dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            from src.services.task_queue import get_task_queue

            get_task_queue().publish_event("portfolio_image_task_updated", summary)
        except Exception as exc:  # pragma: no cover - notification must be fail-open
            logger.debug("图片任务 SSE 通知失败: %s", type(exc).__name__)


def get_portfolio_image_task_manager() -> PortfolioImageTaskManager:
    return PortfolioImageTaskManager()
