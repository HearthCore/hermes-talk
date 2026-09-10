"""Speakable error diagnostics: context without follow-up tool calls."""

from __future__ import annotations

import talk_errors


def test_provider_route_mismatch_explains_cause_and_next_step():
    message = talk_errors.format_failure(
        "background agent run",
        "HTTP 404: /responses is not a registered API route",
        run_id="run_abc",
        status="failed",
    )

    assert "background agent run failed" in message
    assert "provider route mismatch" in message
    assert "HTTP 404" in message
    assert "Responses API" in message
    assert "provider/model pair" in message
    assert "run_abc" in message


def test_rate_limit_explains_wait_or_provider_change():
    message = talk_errors.format_failure(
        "tool execution",
        "HTTP 429: rate limit exceeded",
    )

    assert "rate limit or quota" in message
    assert "wait for the provider cooldown" in message
    assert "same request" in message


def test_auth_failure_keeps_operation_and_action_in_the_sentence():
    message = talk_errors.format_failure(
        "status request",
        "HTTP 401: unauthorized",
    )

    assert "status request failed" in message
    assert "authentication or permission" in message
    assert "credentials" in message


def test_generic_failure_preserves_detail_without_claiming_a_cause():
    message = talk_errors.format_failure(
        "memory lookup",
        "worker crashed before returning a result",
    )

    assert "memory lookup failed" in message
    assert "worker crashed before returning a result" in message
    assert "cause is not known" in message
    assert "inspect the original error" in message
