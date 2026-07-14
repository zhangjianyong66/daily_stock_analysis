# -*- coding: utf-8 -*-
"""Thread-safe in-process caches for realtime bulk provider refreshes."""

import time
from threading import Condition, RLock
from typing import Any, Callable, MutableMapping, Optional


class SingleFlightTTLCache:
    """Coordinate one refresh while concurrent callers reuse its outcome."""

    def __init__(
        self,
        state: MutableMapping[str, Any],
        *,
        failure_ttl_seconds: float = 5.0,
    ) -> None:
        self._state = state
        self._condition = Condition(RLock())
        self._refreshing = False
        self._generation = 0
        self._last_error: Optional[BaseException] = None
        self._failure_expires_at = 0.0
        self._failure_ttl_seconds = max(0.0, float(failure_ttl_seconds))

    def clear(self) -> None:
        with self._condition:
            self._state["data"] = None
            self._state["timestamp"] = 0
            self._refreshing = False
            self._generation += 1
            self._last_error = None
            self._failure_expires_at = 0.0
            self._condition.notify_all()

    def _fresh_data_locked(self) -> Any:
        data = self._state.get("data")
        timestamp = float(self._state.get("timestamp") or 0)
        ttl = max(0.0, float(self._state.get("ttl") or 0))
        if data is not None and time.time() - timestamp < ttl:
            return data
        return None

    def get_or_refresh(
        self,
        loader: Callable[[], Any],
        *,
        wait_timeout_seconds: float,
    ) -> Any:
        wait_timeout = max(0.0, float(wait_timeout_seconds))
        deadline = time.monotonic() + wait_timeout

        with self._condition:
            fresh = self._fresh_data_locked()
            if fresh is not None:
                return fresh
            if self._last_error is not None and time.monotonic() < self._failure_expires_at:
                raise self._last_error

            observed_generation = self._generation
            if self._refreshing:
                while self._refreshing and self._generation == observed_generation:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("realtime cache refresh wait timeout")
                    self._condition.wait(timeout=remaining)
                if self._last_error is not None and time.monotonic() < self._failure_expires_at:
                    raise self._last_error
                fresh = self._fresh_data_locked()
                if fresh is not None:
                    return fresh
                raise TimeoutError("realtime cache refresh completed without reusable data")

            self._refreshing = True

        try:
            data = loader()
        except BaseException as exc:
            with self._condition:
                self._last_error = exc
                self._failure_expires_at = time.monotonic() + self._failure_ttl_seconds
                self._refreshing = False
                self._generation += 1
                self._condition.notify_all()
            raise

        with self._condition:
            self._state["data"] = data
            self._state["timestamp"] = time.time()
            self._last_error = None
            self._failure_expires_at = 0.0
            self._refreshing = False
            self._generation += 1
            self._condition.notify_all()
            return data
