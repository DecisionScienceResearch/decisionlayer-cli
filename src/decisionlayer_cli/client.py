"""DecisionLayer public API client (v1)."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Mapping, Sequence

import httpx

from .errors import APIError, ConfigError, raise_for_status


DEFAULT_BASE_URL = "https://www.decisionlayer.ai"
API_PREFIX = "/api/v1"
MAX_DIRECT_FILE_BYTES = 100 * 1024 * 1024


class DecisionLayerClient:
    """Thin HTTP client for every public v1 endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key or api_key.startswith("PASTE_") or api_key == "dvarb_your_key_here":
            raise ConfigError(
                "No API key configured. Create one at "
                "https://www.decisionlayer.ai/settings/api-keys and run "
                "`dl config set-key` or set DECISIONLAYER_API_KEY."
            )
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": "decisionlayer-cli/1.0.0",
            },
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "DecisionLayerClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _url(self, path: str) -> str:
        return f"{API_PREFIX}{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        files: Any = None,
        expected: Sequence[int] = (200, 201),
    ) -> Any:
        response = self._client.request(
            method,
            self._url(path),
            params=params,
            json=json,
            data=data,
            files=files,
        )
        raise_for_status(response, expected=expected)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def create_upload_sessions(self, files: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        payload = {
            "files": [
                {
                    "filename": item["filename"],
                    "size": item["size"],
                    **({"content_type": item["content_type"]} if item.get("content_type") else {}),
                    **({"role": item["role"]} if item.get("role") else {}),
                }
                for item in files
            ]
        }
        return self._request("POST", "/uploads", json=payload)

    def put_file(self, upload_url: str, path: Path, content_type: str | None = None) -> None:
        mime = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        if len(data) > MAX_DIRECT_FILE_BYTES:
            raise APIError(
                f"{path.name} is {len(data)} bytes; the API limit is 100 MiB per file.",
                status_code=413,
            )
        response = httpx.put(
            upload_url,
            content=data,
            headers={
                "Content-Type": mime,
                "Content-Length": str(len(data)),
            },
            timeout=120.0,
        )
        if response.status_code not in (200, 201, 204):
            raise APIError(
                f"Direct upload of {path.name} failed",
                status_code=response.status_code,
                details=[response.text[:400]],
            )

    def cancel_uploads(self, tickets: Sequence[str]) -> dict[str, Any]:
        return self._request("POST", "/uploads/cancel", json={"tickets": list(tickets)})

    def cancel_upload_sessions(self, tickets: Sequence[str]) -> dict[str, Any]:
        return self.cancel_uploads(tickets)

    def upload_files(self, paths: Sequence[Path], *, role: str | None = None) -> list[str]:
        descriptors = []
        for path in paths:
            if not path.is_file():
                raise ConfigError(f"File not found: {path}")
            size = path.stat().st_size
            if size <= 0:
                raise ConfigError(f"{path} is empty; the upload API requires size > 0.")
            if size > MAX_DIRECT_FILE_BYTES:
                raise ConfigError(f"{path.name} exceeds the 100 MiB per-file limit ({size} bytes).")
            item: dict[str, Any] = {
                "path": path,
                "filename": path.name,
                "size": size,
                "content_type": mimetypes.guess_type(path.name)[0],
            }
            if role:
                item["role"] = role
            descriptors.append(item)
        batch = self.create_upload_sessions(
            [
                {k: v for k, v in d.items() if k != "path"}
                for d in descriptors
            ]
        )
        tickets: list[str] = []
        for session, descriptor in zip(batch["uploads"], descriptors):
            self.put_file(session["upload_url"], descriptor["path"], descriptor["content_type"])
            tickets.append(session["ticket"])
        return tickets

    def list_consent_cases(self) -> list[dict[str, Any]]:
        return self._request("GET", "/consent-cases")

    def create_consent_case(
        self,
        data: Mapping[str, Any],
        *,
        contract_files: Sequence[Path] = (),
        supporting_documents: Sequence[Path] = (),
        via_tickets: bool = False,
    ) -> dict[str, Any]:
        ticket_groups: dict[str, list[str]] = {}
        if via_tickets:
            if contract_files:
                ticket_groups["contract_files_tickets"] = self.upload_files(contract_files)
            if supporting_documents:
                ticket_groups["supporting_documents_tickets"] = self.upload_files(
                    supporting_documents
                )
        form, files = _build_multipart(
            data,
            file_groups={
                "contract_files": [] if via_tickets else contract_files,
                "supporting_documents": [] if via_tickets else supporting_documents,
            },
            ticket_groups=ticket_groups,
        )
        try:
            return self._request("POST", "/consent-cases", files=_as_multipart(form, files))
        finally:
            _close_files(files)

    def list_cases(
        self,
        *,
        action_required: bool | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if action_required is not None:
            params["action_required"] = "true" if action_required else "false"
        if status:
            params["status"] = status
        return self._request("GET", "/cases", params=params)

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self._request("GET", f"/cases/{case_id}")

    def create_case(
        self,
        data: Mapping[str, Any],
        *,
        contract_file: Path | None = None,
        evidence: Sequence[Path] = (),
        via_tickets: bool = False,
    ) -> dict[str, Any]:
        ticket_groups: dict[str, list[str]] = {}
        extra_files: list[tuple[str, tuple[str, BinaryIO, str]]] = []
        handles: list[BinaryIO] = []
        files: list[tuple[str, tuple[str, BinaryIO, str]]] = []
        file_groups: dict[str, Sequence[Path]] = {}

        if via_tickets:
            if contract_file:
                ticket_groups["contract_file_ticket"] = self.upload_files([contract_file])[:1]
            if evidence:
                ticket_groups["evidence_tickets"] = self.upload_files(evidence)
        else:
            if contract_file:
                if not contract_file.is_file():
                    raise ConfigError(f"File not found: {contract_file}")
                handle = contract_file.open("rb")
                handles.append(handle)
                extra_files.append(("contract_file", (contract_file.name, handle, _mime(contract_file))))
            file_groups["evidence"] = evidence

        try:
            form, files = _build_multipart(
                data,
                file_groups=file_groups,
                ticket_groups=ticket_groups,
                extra_files=extra_files,
            )
            return self._request("POST", "/cases", files=_as_multipart(form, files))
        finally:
            _close_files(files)
            for handle in handles:
                if not handle.closed:
                    handle.close()

    def list_responses(self, case_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/cases/{case_id}/responses")

    def create_response(
        self,
        case_id: str,
        data: Mapping[str, Any],
        *,
        evidence: Sequence[Path] = (),
        evidence_response_files: Sequence[Path] = (),
        counterclaim_files: Sequence[Path] = (),
        via_tickets: bool = False,
    ) -> dict[str, Any]:
        ticket_groups: dict[str, list[str]] = {}
        file_groups: dict[str, Sequence[Path]] = {}
        if via_tickets:
            if evidence:
                ticket_groups["evidence_tickets"] = self.upload_files(evidence)
            if evidence_response_files:
                ticket_groups["evidence_response_files_tickets"] = self.upload_files(
                    evidence_response_files
                )
            if counterclaim_files:
                ticket_groups["counterclaim_files_tickets"] = self.upload_files(counterclaim_files)
        else:
            file_groups = {
                "evidence": evidence,
                "evidence_response_files": evidence_response_files,
                "counterclaim_files": counterclaim_files,
            }
        form, files = _build_multipart(
            data,
            file_groups=file_groups,
            ticket_groups=ticket_groups,
        )
        try:
            return self._request(
                "POST",
                f"/cases/{case_id}/responses",
                files=_as_multipart(form, files),
            )
        finally:
            _close_files(files)


def _mime(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _close_files(files: Sequence[tuple[str, tuple[str, BinaryIO, str]]]) -> None:
    for _field, payload in files:
        handle = payload[1]
        if hasattr(handle, "closed") and not handle.closed:
            handle.close()


def _build_multipart(
    data: Mapping[str, Any],
    *,
    file_groups: Mapping[str, Sequence[Path]] | None = None,
    ticket_groups: Mapping[str, Sequence[str]] | None = None,
    extra_files: Iterable[tuple[str, tuple[str, BinaryIO, str]]] = (),
) -> tuple[dict[str, Any], list[tuple[str, tuple[str, BinaryIO, str]]]]:
    form: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, bool):
            form[key] = "true" if value else "false"
            continue
        text = str(value)
        if text == "":
            continue
        form[key] = text

    files: list[tuple[str, tuple[str, BinaryIO, str]]] = list(extra_files)
    for field, paths in (file_groups or {}).items():
        for path in paths:
            if not path.is_file():
                raise ConfigError(f"File not found: {path}")
            handle = path.open("rb")
            files.append((field, (path.name, handle, _mime(path))))

    for field, tickets in (ticket_groups or {}).items():
        if not tickets:
            continue
        if field.endswith("_tickets"):
            form[field] = list(tickets)
        else:
            form[field] = tickets[0]

    return form, files


def _as_multipart(
    form: Mapping[str, Any],
    files: Sequence[tuple[str, tuple[str, BinaryIO, str]]],
) -> list[tuple[str, Any]]:
    """Force multipart/form-data. FastAPI case endpoints reject urlencoded bodies."""
    parts: list[tuple[str, Any]] = []
    for key, value in form.items():
        if isinstance(value, list):
            for item in value:
                parts.append((key, (None, str(item))))
        else:
            parts.append((key, (None, str(value))))
    parts.extend(files)
    return parts
