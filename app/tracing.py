import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Protocol

from .logging_utils import get_request_id, log_extra


class AgentTracer(Protocol):
    """
    Lightweight tracing interface for agent runs.
    Implementations should never raise; failures are swallowed by the caller.
    """

    def record(self, phase: str, **data: Any) -> None:  # pragma: no cover - protocol
        ...


@dataclass
class TraceEvent:
    phase: str
    data: Dict[str, Any] = field(default_factory=dict)


class NullTracer:
    """No-op tracer used by default to avoid overhead."""

    def record(self, phase: str, **data: Any) -> None:
        return None


class InMemoryTracer:
    """Collects trace events in memory; useful for tests and debugging."""

    def __init__(self):
        self.events: List[TraceEvent] = []

    def record(self, phase: str, **data: Any) -> None:
        self.events.append(TraceEvent(phase=phase, data=data))


class LoggingTracer:
    """Emits trace events to structured logs for observability."""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("app.tracer")

    def record(self, phase: str, **data: Any) -> None:
        self.logger.info("trace_event %s %s", phase, data, extra=log_extra(phase=phase, **data))


class FileTracer:
    """
    Appends trace events to a JSONL file for offline analysis and dataset generation.
    Each line: {"phase": "...", "data": {...}, "request_id": "...", "ts": "..."}
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, phase: str, **data: Any) -> None:
        event = {
            "phase": phase,
            "data": data,
            "request_id": get_request_id(),
            "ts": logging.Formatter().formatTime(
                logging.LogRecord(
                    name="app.tracer",
                    level=logging.INFO,
                    pathname=__file__,
                    lineno=0,
                    msg=phase,
                    args=(),
                    exc_info=None,
                )
            ),
        }
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception as exc:  # pragma: no cover - defensive
            logging.getLogger("app.tracer").warning("file_trace_failed %s", exc, extra=log_extra(path=str(self.path)))


class MultiTracer:
    """Fan-out tracer to multiple sinks."""

    def __init__(self, tracers: List[AgentTracer]):
        self.tracers = tracers

    def record(self, phase: str, **data: Any) -> None:
        for tracer in self.tracers:
            try:
                tracer.record(phase, **data)
            except Exception:
                # Best-effort: do not let tracing break agent execution
                continue
