"""OpenTelemetry tracing facade.

Thin wrapper over the OpenTelemetry API so the rest of the codebase doesn't import
it directly. When ``opentelemetry-api`` isn't installed (the default), every helper
no-ops. Configuration is driven by OTel's standard ``OTEL_*`` environment variables
(``OTEL_SERVICE_NAME``, ``OTEL_EXPORTER_OTLP_ENDPOINT``, etc.).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Iterator

try:
    from opentelemetry import trace as _trace
    from opentelemetry.trace import Link as _Link

    _tracer = _trace.get_tracer("ballsdex")
except ImportError:
    _trace = None  # type: ignore[assignment]
    _Link = None  # type: ignore[assignment]
    _tracer = None

if TYPE_CHECKING:
    from opentelemetry.trace import Span, SpanContext


def enabled() -> bool:
    return _tracer is not None


@contextmanager
def span(
    name: str,
    *,
    resource: str | None = None,
    tags: dict[str, Any] | None = None,
    links: list["SpanContext | None"] | None = None,
) -> Iterator["Span | None"]:
    """Start an OTel span. No-op when ``opentelemetry-api`` isn't installed.

    ``resource`` is a Datadog-specific concept (the "operation name within a
    service" that drives Datadog's resource breakdown). OTel has no equivalent
    field, so we set it as a ``resource.name`` attribute — the Datadog Agent's
    OTLP ingester maps this back to the native ``resource`` field, and other
    backends just see it as a regular attribute.

    ``tags`` entries with ``None`` values are dropped so call sites can pass
    ``{"discord.guild.id": interaction.guild_id}`` without branching.
    """
    if _tracer is None or _Link is None:
        yield None
        return
    otel_links = [_Link(ctx) for ctx in (links or []) if ctx is not None] or None
    with _tracer.start_as_current_span(name, links=otel_links) as s:
        if resource:
            s.set_attribute("resource.name", resource)
        if tags:
            for k, v in tags.items():
                if v is not None:
                    s.set_attribute(k, v)
        yield s


def current_trace_context() -> "SpanContext | None":
    """Return the ``SpanContext`` of the currently active span, or ``None``."""
    if _trace is None:
        return None
    span = _trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return None
    return ctx


def set_tag(key: str, value: Any) -> None:
    """Set an attribute on the currently active span.

    No-op when tracing is disabled, no span is active, or value is ``None``.
    """
    if _trace is None or value is None:
        return
    span = _trace.get_current_span()
    if not span.get_span_context().is_valid:
        return
    span.set_attribute(key, value)
