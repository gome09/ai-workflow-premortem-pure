# tests/test_target_http_resilience.py
"""Phase 2 target HTTP hardening: byte caps, streaming, bounded error text."""

from __future__ import annotations

import httpx
import pytest

from core.target_testing import HttpJsonTargetAdapter, TargetSystemConfig

_ENDPOINT = "http://target.local/eval"


def _config(endpoint: str = _ENDPOINT, timeout_seconds: float = 5.0) -> TargetSystemConfig:
    return TargetSystemConfig(endpoint=endpoint, timeout_seconds=timeout_seconds)


def _adapter(handler, *, allowed_hosts: str = "target.local", max_chars: int = 4000):
    return HttpJsonTargetAdapter(
        _config(),
        transport=httpx.MockTransport(handler),
        allowed_hosts=allowed_hosts,
        max_response_chars=max_chars,
    )


def test_declared_content_length_over_limit_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": str(50_000_000)},
            content=b"",
        )

    result = _adapter(handler).execute("input")

    assert result.outcome == "error"
    assert result.error_code == "response_too_large"
    assert result.truncated is True
    assert result.status_code == 200
    assert result.response_digest == ""


def test_streamed_body_over_limit_returns_response_too_large():
    chunk = b"y" * 8192

    def handler(request: httpx.Request) -> httpx.Response:
        # 迭代器响应没有 content-length，必须靠流式读取触发上限。
        return httpx.Response(200, content=iter([chunk, chunk, chunk]))

    result = _adapter(handler).execute("input")

    assert result.outcome == "error"
    assert result.error_code == "response_too_large"
    assert result.truncated is True
    assert result.response_digest


def test_large_error_body_message_is_bounded():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=iter([b"x" * 8192, b"x" * 8192]))

    result = _adapter(handler).execute("input")

    assert result.outcome == "failed"
    assert result.error_code == "http_500"
    assert result.truncated is True
    assert len(result.error_message) <= 500


def test_connect_error_maps_to_target_request_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    result = _adapter(handler).execute("input")

    assert result.outcome == "error"
    assert result.error_code == "target_request_error"
    assert "refused" in result.error_message


def test_read_timeout_maps_to_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    result = _adapter(handler).execute("input")

    assert result.outcome == "timeout"
    assert result.error_code == "target_timeout"


def test_host_port_allowlist_match():
    endpoint = "https://target.local:8443/eval"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output": "ok"})

    adapter = HttpJsonTargetAdapter(
        _config(endpoint),
        transport=httpx.MockTransport(handler),
        allowed_hosts="target.local:8443",
    )

    result = adapter.execute("input")

    assert result.outcome == "success"
    assert result.output == "ok"


def test_empty_allowlist_is_fail_closed():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"output": "should not happen"})

    adapter = HttpJsonTargetAdapter(
        _config(),
        transport=httpx.MockTransport(handler),
        allowed_hosts="",
    )

    result = adapter.execute("input")

    assert result.outcome == "error"
    assert result.error_code == "endpoint_not_allowed"
    assert calls == []


def test_success_output_is_truncated_by_char_cap():
    long_output = "a" * 5000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output": long_output})

    result = _adapter(handler, max_chars=4000).execute("input")

    assert result.outcome == "success"
    assert len(result.output) == 4000
    assert result.truncated is True


@pytest.mark.parametrize("status_code", [301, 404, 429])
def test_non_2xx_status_is_failed_outcome(status_code):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="upstream says no")

    result = _adapter(handler).execute("input")

    assert result.outcome == "failed"
    assert result.status_code == status_code
    assert result.error_code == f"http_{status_code}"
