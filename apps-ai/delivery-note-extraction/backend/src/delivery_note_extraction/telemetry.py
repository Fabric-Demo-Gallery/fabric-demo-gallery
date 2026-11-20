import os
from contextlib import contextmanager
from functools import lru_cache
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

AGENT_ID = os.getenv("OTEL_AGENT_ID", "delivery-note-extraction")


@lru_cache
def setup_telemetry() -> bool:
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
        from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
    except ImportError:
        return False

    # Cloud role name in Application Insights / Foundry (otherwise
    # "unknown_service").
    os.environ.setdefault("OTEL_SERVICE_NAME", AGENT_ID)
    configure_azure_monitor(connection_string=connection_string)
    OpenAIInstrumentor().instrument()
    return True


def instrument_app(app: "FastAPI") -> None:
    """Attach the OpenTelemetry ASGI middleware to an existing FastAPI app.

    app.py imports the FastAPI class before setup_telemetry() runs, so the
    global auto-instrumentation patch misses this app instance and no server
    spans would be emitted. Health routes are excluded to keep probe noise
    out, and ASGI-internal receive/send sub-spans are dropped: they add no
    insight here and the SSE stream endpoint would emit one per chunk.
    """
    if not setup_telemetry():
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        return
    FastAPIInstrumentor.instrument_app(
        app, excluded_urls="health$", exclude_spans=["receive", "send"]
    )


@contextmanager
def agent_span(name: str) -> Iterator[None]:
    """Wrap work in a span tagged with gen_ai.agent.id for Foundry attribution.

    No-op when OpenTelemetry isn't installed/configured.
    """
    try:
        from opentelemetry import trace
    except ImportError:
        yield
        return

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(name) as span:
        # invoke_agent semantics let Foundry classify the root span as an
        # agent invocation instead of "Other" and propagate main-agent
        # attribution to child spans.
        span.set_attribute("gen_ai.operation.name", "invoke_agent")
        span.set_attribute("gen_ai.agent.id", AGENT_ID)
        span.set_attribute("gen_ai.agent.name", AGENT_ID)
        yield


AttributeValue = str | bool | int | float


@contextmanager
def stage_span(name: str) -> Iterator["StageSpan"]:
    """Wrap a pipeline stage in a span and expose attribute/event helpers.

    No-op when OpenTelemetry isn't installed/configured.
    """
    try:
        from opentelemetry import trace
    except ImportError:
        yield StageSpan(None)
        return

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(name) as span:
        yield StageSpan(span)


class StageSpan:
    def __init__(self, span: object | None) -> None:
        self._span = span

    def set_attributes(self, attributes: dict[str, AttributeValue]) -> None:
        if self._span is not None:
            for key, value in attributes.items():
                self._span.set_attribute(key, value)  # type: ignore[attr-defined]

    def add_event(self, name: str, attributes: dict[str, AttributeValue]) -> None:
        if self._span is not None:
            self._span.add_event(name, attributes=attributes)  # type: ignore[attr-defined]
