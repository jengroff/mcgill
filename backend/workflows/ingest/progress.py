from __future__ import annotations

from typing import Callable

ProgressCallback = Callable[[str, str, int, int], None]

_sinks: dict[str, ProgressCallback] = {}


def register(run_id: str, callback: ProgressCallback) -> None:
    _sinks[run_id] = callback


def unregister(run_id: str) -> None:
    _sinks.pop(run_id, None)


def get(run_id: str) -> ProgressCallback | None:
    return _sinks.get(run_id)
