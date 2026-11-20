from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

AGENT_ID = os.getenv("OTEL_AGENT_ID", "demand-portfolio-planning")

AttributeValue = str | bool | int | float

# Domain string attributes can be large; cap so spans stay within limits.
_MAX_ATTR_CHARS = 8000


@lru_cache
def setup_observability() -> bool:
    """Wire OpenTelemetry GenAI spans to the Foundry project's Application Insights.

    No-op unless APPLICATIONINSIGHTS_CONNECTION_STRING is set, so the app runs
    unchanged when telemetry packages or the connection string are absent.
    Returns True when instrumentation was configured.
    """
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not connection_string:
        return False
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError:
        return False

    configure_azure_monitor(connection_string=connection_string)

    # Agent Framework emits agent / workflow / chat spans through the global tracer
    # provider Azure Monitor just configured; opt into message-content capture.
    try:
        from agent_framework.observability import enable_sensitive_telemetry

        enable_sensitive_telemetry(force=True)
    except Exception:  # pragma: no cover - best effort
        pass

    # OpenAI-level GenAI spans, when the openai SDK is used under the hood.
    try:
        from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

        OpenAIInstrumentor().instrument()  # type: ignore[no-untyped-call]
    except Exception:  # pragma: no cover - best effort
        pass

    return True


def clip(value: str) -> str:
    return value if len(value) <= _MAX_ATTR_CHARS else value[:_MAX_ATTR_CHARS] + "…"


@contextmanager
def stage_span(name: str) -> Iterator[StageSpan]:
    """Wrap a pipeline stage in a span tagged for Foundry agent attribution.

    No-op when OpenTelemetry isn't installed/configured.
    """
    try:
        from opentelemetry import trace
    except ImportError:
        yield StageSpan(None)
        return

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(name) as span:
        span.set_attribute("gen_ai.agent.id", AGENT_ID)
        yield StageSpan(span)


class StageSpan:
    def __init__(self, span: object | None) -> None:
        self._span = span

    def set_attributes(self, attributes: dict[str, AttributeValue]) -> None:
        if self._span is None:
            return
        for key, value in attributes.items():
            if isinstance(value, str):
                value = clip(value)
            self._span.set_attribute(key, value)  # type: ignore[attr-defined]

    def add_event(self, name: str, attributes: dict[str, AttributeValue]) -> None:
        if self._span is not None:
            self._span.add_event(name, attributes=attributes)  # type: ignore[attr-defined]
