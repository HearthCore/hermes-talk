"""Bounded, speakable diagnostics for failures already in hand.

This module never probes a provider, calls a tool, or performs remediation. It
only classifies and formats the error data a caller already received.
"""

from __future__ import annotations

import re
from typing import Any

_MAX_DETAIL_CHARS = 900
_HTTP_STATUS_RE = re.compile(r"\b(?:HTTP\s*)?([45]\d{2})\b", re.IGNORECASE)
_BEARER_RE = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,}]+"
)
_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,}]+"
)


def _redact(text: str) -> str:
    text = _BEARER_RE.sub(r"\1[redacted]", text)
    return _SECRET_RE.sub(lambda match: f"{match.group(1)}=[redacted]", text)


def _status_code(detail: str, status: Any) -> int | None:
    if isinstance(status, int) and 400 <= status <= 599:
        return status
    match = _HTTP_STATUS_RE.search(detail)
    return int(match.group(1)) if match else None


def _classify(detail: str, status_code: int | None) -> tuple[str, str, str]:
    lower = detail.lower()

    if (
        status_code == 404
        and "responses" in lower
        and (
            "not registered" in lower
            or "not a registered" in lower
            or "not found" in lower
        )
    ):
        return (
            "provider route mismatch",
            "the selected provider does not expose the Responses API route",
            "use a provider/model pair with Responses API support, or switch the request to that provider's supported chat-completions path",
        )
    if status_code in {401, 403} or any(
        marker in lower for marker in ("unauthorized", "forbidden", "invalid api key")
    ):
        return (
            "authentication or permission",
            "the endpoint rejected the available credentials or access scope",
            "check the configured credentials, endpoint, and required auth mode",
        )
    if status_code == 429 or any(
        marker in lower
        for marker in ("rate limit", "ratelimit", "quota", "usage limit")
    ):
        return (
            "rate limit or quota",
            "the provider refused the request because its usage limit was reached",
            "wait for the provider cooldown or use a configured provider with quota; do not retry the same request immediately",
        )
    if any(
        marker in lower
        for marker in ("insufficient credits", "billing", "payment required", "no credits")
    ):
        return (
            "provider account or credits",
            "the selected provider account cannot fund this request",
            "use a provider with available credits or repair the provider billing configuration",
        )
    if any(
        marker in lower
        for marker in ("timeout", "timed out", "connecterror", "connection refused", "dns")
    ):
        return (
            "connectivity",
            "the endpoint could not be reached within the available time",
            "check endpoint reachability and retry when the service is reachable",
        )
    if status_code is not None and 500 <= status_code <= 599:
        return (
            "upstream service failure",
            "the remote service returned a server-side error",
            "retry after the upstream service recovers; changing the prompt will not fix this response",
        )
    if any(marker in lower for marker in ("cancelled", "canceled", "aborted")):
        return (
            "cancellation",
            "the operation was stopped before it completed",
            "check what cancelled the operation before starting it again",
        )
    return (
        "unknown failure",
        "the cause is not known from the returned error data",
        "inspect the original error and relevant provider or service logs before retrying",
    )


def format_failure(
    operation: str,
    detail: Any,
    *,
    run_id: str | int | None = None,
    status: Any = None,
    provider: str | None = None,
    model: str | None = None,
    endpoint: str | None = None,
    phase: str | None = None,
) -> str:
    """Format already-known failure data as concise, voice-friendly context."""

    clean_operation = str(operation).strip() or "operation"
    clean_detail = _redact(str(detail).strip() or "no detail returned")[:_MAX_DETAIL_CHARS]
    code = _status_code(clean_detail, status)
    category, cause, next_step = _classify(clean_detail, code)

    parts = [
        f"{clean_operation} failed.",
        f"Category: {category}.",
    ]
    if run_id is not None:
        parts.append(f"Run: {run_id}.")
    if phase:
        parts.append(f"Phase: {phase}.")
    if code is not None:
        parts.append(f"HTTP status: {code}.")
    elif status:
        parts.append(f"Status: {status}.")
    if provider:
        parts.append(f"Provider: {provider}.")
    if model:
        parts.append(f"Model: {model}.")
    if endpoint:
        parts.append(f"Endpoint: {endpoint}.")
    parts.extend(
        (
            f"Details: {clean_detail}.",
            f"Likely cause: {cause}.",
            f"Next step: {next_step}.",
            "No additional tool call was made to diagnose this failure.",
        )
    )
    return " ".join(parts)


def format_exception(operation: str, exc: BaseException, **context: Any) -> str:
    """Format an exception without exposing a traceback or secret values."""

    return format_failure(
        operation,
        f"{type(exc).__name__}: {exc}",
        **context,
    )


__all__ = ["format_exception", "format_failure"]
