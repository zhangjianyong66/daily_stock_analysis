# -*- coding: utf-8 -*-
"""Tests for the recoverable in-process portfolio image task state machine."""

from __future__ import annotations

import threading
import time
from datetime import date
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from src.services.portfolio_image_task_manager import (
    PortfolioImageDraftConflictError,
    PortfolioImageTaskActiveError,
    PortfolioImageTaskManager,
    PortfolioImageTaskStateConflictError,
)
from src.services.portfolio_screenshot_import_service import (
    ImageInput,
    PortfolioImageProcessingCancelled,
)


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 12


def _image(index: int = 0) -> ImageInput:
    return ImageInput(PNG_BYTES + bytes([index]), "image/png", f"{index}.png")


def _position_result(*, failed: bool = False) -> Dict[str, Any]:
    return {
        "batch_id": "batch-1",
        "account_id": 7,
        "snapshot_date": "2026-07-14",
        "files": [
            {
                "index": 0,
                "filename": "0.png",
                "status": "failed" if failed else "success",
                "record_count": 0 if failed else 1,
                "error": "vision_timeout" if failed else None,
            }
        ],
        "summary": {},
        "positions": [] if failed else [
            {
                "source_refs": [{"file_index": 0, "row_index": 0}],
                "symbol": "600000",
                "name": "浦发银行",
                "quantity": 100,
                "avg_cost": 10,
                "confidence": "high",
                "status": "ready",
                "issues": [],
            }
        ],
    }


class FakeScreenshotService:
    def __init__(self, result: Dict[str, Any]) -> None:
        self.result = result
        self.calls = 0

    def validate_position_images_request(self, **_: Any) -> Any:
        return SimpleNamespace(name="Main")

    def validate_trade_images_request(self, **_: Any) -> Any:
        return SimpleNamespace(name="Main")

    def validate_uploaded_images(self, images: List[ImageInput]) -> None:
        assert images

    def parse_position_images(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls += 1
        callback = kwargs["progress_callback"]
        callback({"phase": "file_started", "file_index": 0, "total_files": 1})
        callback({"phase": "attempt", "file_index": 0, "total_files": 1, "attempt": 1, "max_attempts": 2})
        file_result = self.result["files"][0]
        callback(
            {
                "phase": "file_completed",
                "file_index": 0,
                "total_files": 1,
                "status": file_result["status"],
                "record_count": file_result["record_count"],
                "error": file_result["error"],
            }
        )
        return self.result

    parse_trade_images = parse_position_images


class BlockingScreenshotService(FakeScreenshotService):
    def __init__(self) -> None:
        super().__init__(_position_result())
        self.started = threading.Event()
        self.release = threading.Event()

    def parse_position_images(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls += 1
        kwargs["progress_callback"](
            {"phase": "attempt", "file_index": 0, "total_files": 1, "attempt": 1, "max_attempts": 2}
        )
        self.started.set()
        self.release.wait(timeout=2)
        if kwargs["cancel_requested"]():
            raise PortfolioImageProcessingCancelled()
        return self.result


def _wait_status(manager: PortfolioImageTaskManager, status: str, timeout: float = 2) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = manager.get_current_task()
        if task and task["status"] == status:
            return task
        time.sleep(0.01)
    raise AssertionError(f"task did not reach status={status}: {manager.get_current_task()}")


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch):
    PortfolioImageTaskManager.reset_instance()
    monkeypatch.setattr(PortfolioImageTaskManager, "_publish_summary", staticmethod(lambda _summary: None))
    instance = PortfolioImageTaskManager()
    yield instance
    PortfolioImageTaskManager.reset_instance()


def test_success_requires_review_and_blocks_duplicate_submission(manager: PortfolioImageTaskManager) -> None:
    service = BlockingScreenshotService()
    accepted = manager.submit_task(
        mode="positions",
        account_id=7,
        date_value=date(2026, 7, 14),
        images=[_image()],
        service=service,
    )
    assert service.started.wait(timeout=1)

    with pytest.raises(PortfolioImageTaskActiveError) as exc_info:
        manager.submit_task(
            mode="trades",
            account_id=8,
            date_value=date(2026, 7, 14),
            images=[_image()],
            service=FakeScreenshotService(_position_result()),
        )
    assert exc_info.value.existing_task_id == accepted["task_id"]
    assert service.calls == 1

    service.release.set()
    task = _wait_status(manager, "review_required")
    assert task["draft_revision"] == 1
    assert task["draft"]["positions"][0]["symbol"] == "600000"


def test_all_files_failed_releases_slot_for_new_submission(manager: PortfolioImageTaskManager) -> None:
    first = manager.submit_task(
        mode="positions",
        account_id=7,
        date_value=date(2026, 7, 14),
        images=[_image()],
        service=FakeScreenshotService(_position_result(failed=True)),
    )
    failed = _wait_status(manager, "failed")
    assert failed["task_id"] == first["task_id"]
    assert failed["error_code"] == "vision_timeout"

    second = manager.submit_task(
        mode="positions",
        account_id=7,
        date_value=date(2026, 7, 14),
        images=[_image()],
        service=FakeScreenshotService(_position_result()),
    )
    assert second["task_id"] != first["task_id"]
    _wait_status(manager, "review_required")


def test_processing_cancel_waits_for_worker_and_late_result_is_ignored(manager: PortfolioImageTaskManager) -> None:
    service = BlockingScreenshotService()
    accepted = manager.submit_task(
        mode="positions",
        account_id=7,
        date_value=date(2026, 7, 14),
        images=[_image()],
        service=service,
    )
    assert service.started.wait(timeout=1)

    cancelling = manager.cancel_task(accepted["task_id"])
    assert cancelling["status"] == "cancel_requested"
    with pytest.raises(PortfolioImageTaskActiveError):
        manager.submit_task(
            mode="positions",
            account_id=7,
            date_value=date(2026, 7, 14),
            images=[_image()],
            service=FakeScreenshotService(_position_result()),
        )

    service.release.set()
    cancelled = _wait_status(manager, "cancelled")
    assert cancelled["draft"] is None


def test_pending_task_can_be_cancelled_before_worker_starts(manager: PortfolioImageTaskManager) -> None:
    gate = threading.Event()
    assert manager._executor is not None
    blocker = manager._executor.submit(lambda: gate.wait(timeout=2))
    accepted = manager.submit_task(
        mode="positions",
        account_id=7,
        date_value=date(2026, 7, 14),
        images=[_image()],
        service=FakeScreenshotService(_position_result()),
    )

    cancelled = manager.cancel_task(accepted["task_id"])
    assert cancelled["status"] == "cancelled"
    gate.set()
    blocker.result(timeout=1)


def test_draft_revision_and_two_phase_commit(manager: PortfolioImageTaskManager) -> None:
    accepted = manager.submit_task(
        mode="positions",
        account_id=7,
        date_value=date(2026, 7, 14),
        images=[_image()],
        service=FakeScreenshotService(_position_result()),
    )
    review = _wait_status(manager, "review_required")

    updated = manager.update_draft(
        accepted["task_id"],
        expected_revision=1,
        files=[{"index": 0, "removed": False}],
        positions=[{**review["draft"]["positions"][0], "quantity": 200}],
    )
    assert updated["draft_revision"] == 2
    assert updated["draft"]["positions"][0]["quantity"] == 200
    with pytest.raises(PortfolioImageDraftConflictError):
        manager.update_draft(
            accepted["task_id"],
            expected_revision=1,
            files=[{"index": 0, "removed": False}],
            positions=updated["draft"]["positions"],
        )

    manager.begin_commit(
        accepted["task_id"],
        mode="positions",
        account_id=7,
        batch_id="batch-1",
        expected_revision=2,
        date_value=date(2026, 7, 14),
    )
    assert manager.get_current_task()["status"] == "committing"
    manager.rollback_commit(accepted["task_id"])
    assert manager.get_current_task()["status"] == "review_required"
    manager.begin_commit(
        accepted["task_id"],
        mode="positions",
        account_id=7,
        batch_id="batch-1",
        expected_revision=2,
        date_value=date(2026, 7, 14),
    )
    manager.finish_commit(accepted["task_id"])
    assert manager.get_current_task() is None


def test_batch_deadline_marks_task_failed(manager: PortfolioImageTaskManager) -> None:
    service = BlockingScreenshotService()
    accepted = manager.submit_task(
        mode="positions",
        account_id=7,
        date_value=date(2026, 7, 14),
        images=[_image()],
        service=service,
        deadline_seconds=0.02,
    )
    assert service.started.wait(timeout=1)
    time.sleep(0.03)
    service.release.set()
    failed = _wait_status(manager, "failed")
    assert failed["task_id"] == accepted["task_id"]
    assert failed["error_code"] == "portfolio_image_task_timeout"


def test_failed_files_must_be_removed_before_commit(manager: PortfolioImageTaskManager) -> None:
    result = _position_result()
    result["files"].append(
        {"index": 1, "filename": "1.png", "status": "failed", "record_count": 0, "error": "invalid_image"}
    )
    accepted = manager.submit_task(
        mode="positions",
        account_id=7,
        date_value=date(2026, 7, 14),
        images=[_image(0), _image(1)],
        service=FakeScreenshotService(result),
    )
    review = _wait_status(manager, "review_required")

    with pytest.raises(PortfolioImageTaskStateConflictError, match="移除"):
        manager.begin_commit(
            accepted["task_id"],
            mode="positions",
            account_id=7,
            batch_id="batch-1",
            expected_revision=1,
            date_value=date(2026, 7, 14),
        )

    manager.update_draft(
        accepted["task_id"],
        expected_revision=1,
        files=[{"index": 0, "removed": False}, {"index": 1, "removed": True}],
        positions=review["draft"]["positions"],
    )
    manager.begin_commit(
        accepted["task_id"],
        mode="positions",
        account_id=7,
        batch_id="batch-1",
        expected_revision=2,
        date_value=date(2026, 7, 14),
    )
    assert manager.get_current_task()["status"] == "committing"


def test_service_restart_drops_in_memory_task_and_slot(manager: PortfolioImageTaskManager) -> None:
    manager.submit_task(
        mode="positions",
        account_id=7,
        date_value=date(2026, 7, 14),
        images=[_image()],
        service=FakeScreenshotService(_position_result()),
    )
    _wait_status(manager, "review_required")

    PortfolioImageTaskManager.reset_instance()
    restarted = PortfolioImageTaskManager()

    assert restarted.get_current_task() is None
