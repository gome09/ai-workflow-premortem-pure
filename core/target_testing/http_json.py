# core/target_testing/http_json.py
"""Generic HTTP JSON adapter for real target-system evaluation runs."""

from __future__ import annotations

import hashlib
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from core.config import settings
from core.llm.outbound_guard import should_mask
from core.target_testing.models import TargetSystemConfig, TargetTestResponse
from tools.safety_classifier import mask_pii_in_text


def sanitize_endpoint(endpoint: str) -> str:
    """Validate and normalize a target endpoint for audit storage."""
    raw = (endpoint or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Unsupported target endpoint: {endpoint!r}")
    netloc = parsed.hostname.lower()
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    path = parsed.path or ""
    return urlunparse((parsed.scheme, netloc, path, "", "", ""))


def _allowed_hosts() -> set[str]:
    return {
        item.strip().lower()
        for item in (settings.target_system_allowed_hosts or "").split(",")
        if item.strip()
    }


def _host_candidates(sanitized: str) -> set[str]:
    parsed = urlparse(sanitized)
    host = (parsed.hostname or "").lower()
    default_port = 443 if parsed.scheme == "https" else 80
    port = parsed.port or default_port
    return {host, f"{host}:{port}"}


def endpoint_is_allowed(sanitized: str) -> bool:
    """Fail-closed SSRF guard: an empty allowlist denies every host."""
    allowed = _allowed_hosts()
    if not allowed:
        return False
    return bool(_host_candidates(sanitized).intersection(allowed))


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


class HttpJsonTargetAdapter:
    """Execute one eval input against a real HTTP JSON target."""

    def __init__(
        self,
        config: TargetSystemConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        allowed_hosts: str | None = None,
        token: str | None = None,
        max_response_chars: int | None = None,
    ) -> None:
        self.config = config
        self._transport = transport
        self._allowed_hosts = allowed_hosts
        self._token = token
        self._max_response_chars = max_response_chars

    def _allowed(self, sanitized: str) -> bool:
        if self._allowed_hosts is not None:
            allowed = {
                item.strip().lower() for item in self._allowed_hosts.split(",") if item.strip()
            }
            if not allowed:
                return False
            return bool(_host_candidates(sanitized).intersection(allowed))
        return endpoint_is_allowed(sanitized)

    def execute(
        self,
        input_payload: str,
        *,
        session_id: str = "",
        eval_id: str = "",
        node_id: str | None = None,
        classification: str = "business_internal",
    ) -> TargetTestResponse:
        try:
            endpoint = sanitize_endpoint(self.config.endpoint)
        except ValueError as exc:
            return TargetTestResponse(
                outcome="error",
                error_code="invalid_endpoint",
                error_message=str(exc),
            )

        if not self._allowed(endpoint):
            return TargetTestResponse(
                outcome="error",
                error_code="endpoint_not_allowed",
                error_message=(
                    "Target endpoint host is not in TARGET_SYSTEM_ALLOWED_HOSTS; "
                    "configure the allowlist explicitly."
                ),
                endpoint=endpoint,
            )

        payload = input_payload
        if should_mask(classification):
            payload = mask_pii_in_text(payload)

        headers = {"Content-Type": "application/json"}
        token = self._token if self._token is not None else settings.target_system_token
        if token:
            headers["Authorization"] = f"Bearer {token}"

        body = {
            "input": payload,
            "session_id": session_id,
            "eval_id": eval_id,
            "node_id": node_id,
        }
        max_chars = (
            self._max_response_chars
            if self._max_response_chars is not None
            else settings.target_system_max_response_chars
        )

        started = time.monotonic()
        try:
            with httpx.Client(
                timeout=self.config.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(endpoint, json=body, headers=headers)
            latency_ms = int((time.monotonic() - started) * 1000)
        except httpx.TimeoutException as exc:
            return TargetTestResponse(
                outcome="timeout",
                latency_ms=int((time.monotonic() - started) * 1000),
                error_code="target_timeout",
                error_message=str(exc) or "Target request timed out",
                endpoint=endpoint,
            )
        except httpx.RequestError as exc:
            return TargetTestResponse(
                outcome="error",
                latency_ms=int((time.monotonic() - started) * 1000),
                error_code="target_request_error",
                error_message=str(exc),
                endpoint=endpoint,
            )
        except Exception as exc:  # noqa: BLE001 - transport errors are eval evidence
            return TargetTestResponse(
                outcome="error",
                latency_ms=int((time.monotonic() - started) * 1000),
                error_code="target_unexpected_error",
                error_message=str(exc),
                endpoint=endpoint,
            )

        raw_text = response.text or ""
        response_digest = _digest_text(raw_text)
        text = raw_text
        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True
        if should_mask(classification):
            text = mask_pii_in_text(text)

        if response.status_code < 200 or response.status_code >= 300:
            return TargetTestResponse(
                outcome="failed",
                status_code=response.status_code,
                latency_ms=latency_ms,
                error_code=f"http_{response.status_code}",
                error_message=text,
                endpoint=endpoint,
                response_digest=response_digest,
                truncated=truncated,
            )

        try:
            data: Any = response.json()
        except ValueError:
            return TargetTestResponse(
                outcome="error",
                status_code=response.status_code,
                latency_ms=latency_ms,
                error_code="response_contract_error",
                error_message="Target response is not valid JSON.",
                endpoint=endpoint,
                response_digest=response_digest,
                truncated=truncated,
            )

        output = data.get(self.config.output_field) if isinstance(data, dict) else None
        if not isinstance(output, str):
            return TargetTestResponse(
                outcome="error",
                status_code=response.status_code,
                latency_ms=latency_ms,
                error_code="response_contract_error",
                error_message=(
                    f"Target response does not contain string field {self.config.output_field!r}."
                ),
                endpoint=endpoint,
                response_digest=response_digest,
                truncated=truncated,
            )

        if len(output) > max_chars:
            output = output[:max_chars]
            truncated = True
        if should_mask(classification):
            output = mask_pii_in_text(output)

        return TargetTestResponse(
            outcome="success",
            output=output,
            status_code=response.status_code,
            latency_ms=latency_ms,
            endpoint=endpoint,
            response_digest=response_digest,
            truncated=truncated,
        )
