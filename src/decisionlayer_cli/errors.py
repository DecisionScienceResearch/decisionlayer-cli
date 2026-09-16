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
        self.body = body

    def __str__(self) -> str:
        lines = [f"HTTP {self.status_code}: {self.message}"]
        for detail in self.details:
            lines.append(f"  - {detail}")
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


def raise_for_status(response: httpx.Response, expected: Sequence[int] = (200, 201)) -> None:
    if response.status_code in expected:
        return
    try:
        body: Any = response.json()
    except Exception:
        body = {"raw": response.text[:800]}
    message, details = parse_error_body(body)
    raise APIError(
        message,
        status_code=response.status_code,
        details=details,
        hint=_hint(response.status_code),
        body=body,
    )


def parse_error(status_code: int, body: Any, url: str | None = None) -> APIError:
    message, details = parse_error_body(body)
    return APIError(
        message,
        status_code=status_code,
        details=details,
        hint=_hint(status_code),
        body=body,
    )


def _hint(status: int) -> str:
    return {
        401: "Create or paste a key from /settings/api-keys (prefix dvarb_).",
        403: "Case filing is limited to approved accounts. Email casemanager@decisionlayer.ai.",
        404: "The case does not exist, or this API key is not a party to it.",
        409: "Wrong turn, unfinished web step, already submitted, or an upload PUT is incomplete.",
        413: "A file exceeded the 100 MiB per-file limit.",
        422: "Fix the listed fields. Do not mix multipart files with upload tickets on the same field.",
    }.get(status, "")
