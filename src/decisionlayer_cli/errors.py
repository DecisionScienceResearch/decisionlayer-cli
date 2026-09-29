"""Error types matching DecisionLayer's documented JSON error envelope."""

from __future__ import annotations

from typing import Any, Sequence

import httpx


class DecisionLayerError(Exception):
    """Base error for the CLI."""


class ConfigError(DecisionLayerError):
    """Missing keys, files, or local usage mistakes."""


class APIError(DecisionLayerError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        details: list[str] | None = None,
        hint: str = "",
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or []
        self.hint = hint
        self.reason = ""
        self.body = body

    def __str__(self) -> str:
        lines = [f"HTTP {self.status_code}: {self.message}"]
        for detail in self.details:
            lines.append(f"  - {detail}")
        if self.reason:
            lines.append(f"reason: {self.reason}")
        if self.hint:
            lines.append(self.hint)
        return "\n".join(lines)


def parse_error_body(body: Any) -> tuple[str, list[str]]:
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        error = body["error"]
        message = str(error.get("message") or "Request failed.")
        raw_details = error.get("details") or []
        return message, [str(item) for item in raw_details]
    if isinstance(body, dict) and "detail" in body:
        detail = body["detail"]
        if isinstance(detail, list):
            details = []
            for item in detail:
                if isinstance(item, dict):
                    loc = ".".join(str(part) for part in item.get("loc", []) if part != "body")
                    msg = item.get("msg", "invalid")
                    details.append(f"{loc}: {msg}" if loc else str(msg))
                else:
                    details.append(str(item))
            return "Validation failed.", details
        return str(detail), []
    if isinstance(body, dict) and body.get("message"):
        return str(body["message"]), []
    return "Request failed.", []


def error_reason(body: Any) -> str:
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        reason = body["error"].get("reason")
        if reason:
            return str(reason)
    return ""


def raise_for_status(response: httpx.Response, expected: Sequence[int] = (200, 201)) -> None:
    if response.status_code in expected:
        return
    try:
        body: Any = response.json()
    except Exception:
        body = {"raw": response.text[:800]}
    message, details = parse_error_body(body)
    reason = error_reason(body)
    error = APIError(
        message,
        status_code=response.status_code,
        details=details,
        hint=_hint(response.status_code, reason),
        body=body,
    )
    error.reason = reason
    if details and not reason:
        error.hint = ""
    raise error


def parse_error(status_code: int, body: Any, url: str | None = None) -> APIError:
    message, details = parse_error_body(body)
    reason = error_reason(body)
    error = APIError(
        message,
        status_code=status_code,
        details=details,
        hint=_hint(status_code, reason),
        body=body,
    )
    error.reason = reason
    return error


def _hint(status: int, reason: str = "") -> str:
    if status == 404 and reason == "not_claimed":
        return "The respondent has not claimed this case. Run `dl case claim` with the verification code from the notice."
    if status == 404 and reason == "not_a_party":
        return "This API key is not a party on the case. Switch to the claimant or respondent profile that is."
    if status == 404 and reason == "not_found":
        return "Nothing with that id exists for this key."
    return {
        401: "Create or paste a key from /settings/api-keys (prefix dvarb_). Test keys use /settings/test-api-keys (prefix dvarb_test_).",
        403: "The key is not allowed to do this. Filing can require an approved account, simulations reject test keys, and the consent respondent shortcut rejects live keys.",
        404: "The resource does not exist, or this API key cannot see it. Case 404s include error.reason.",
        409: "Wrong turn, unfinished web step, already submitted, an upload PUT is incomplete, or this Idempotency-Key does not match the previous body.",
        413: "A file exceeded the 100 MiB per-file limit.",
        422: "Fix the listed fields. Do not mix multipart files with upload tickets on the same field.",
        429: "The monthly simulation limit is exhausted. Wait until it resets before creating another simulation.",
    }.get(status, "")
