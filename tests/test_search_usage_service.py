from __future__ import annotations

from datetime import datetime, timezone

from src.services.search_usage_service import SearchUsageService


class FakeRepo:
    def __init__(self):
        self.events = []
        self.resolved = []

    def insert_call(self, values):
        self.events.append(values)
        return len(self.events)

    def resolve_faults(self, provider, key_fingerprint, resolved_at):
        return []

    def record_fault_event(self, **kwargs):
        count = sum(1 for item in self.events if item.get("error_category") == kwargs["category"])
        fault = {
            "id": 1,
            "provider": kwargs["provider"],
            "key_fingerprint": kwargs["key_fingerprint"],
            "error_category": kwargs["category"],
        }
        return fault, kwargs["immediate"] or count >= kwargs["threshold"]

    def insert_gap(self, **kwargs):
        return None


def call_values(category: str):
    return {
        "provider": "Anspire",
        "key_fingerprint": "abc",
        "success": False,
        "error_category": category,
        "error_summary": category,
        "completed_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "logical_request_id": "logical",
    }


def test_immediate_fault_activates_on_first_failure(monkeypatch):
    repo = FakeRepo()
    service = SearchUsageService(repo=repo)
    notified = []
    monkeypatch.setattr(service, "_notify_async", lambda fault, recovery: notified.append((fault, recovery)))
    service.record_physical_call(call_values("quota_exhausted"))
    assert len(notified) == 1
    assert notified[0][1] is False


def test_transient_fault_activates_on_third_consecutive_failure(monkeypatch):
    repo = FakeRepo()
    service = SearchUsageService(repo=repo)
    notified = []
    monkeypatch.setattr(service, "_notify_async", lambda fault, recovery: notified.append((fault, recovery)))
    for _ in range(3):
        service.record_physical_call(call_values("timeout"))
    assert len(notified) == 1
