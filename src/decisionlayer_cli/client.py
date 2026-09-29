"""DecisionLayer public API client (v1)."""

from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Mapping, Sequence

import httpx

from . import __version__
from .errors import APIError, ConfigError, raise_for_status


DEFAULT_BASE_URL = "https://www.decisionlayer.ai"
API_PREFIX = "/api/v1"
MAX_DIRECT_FILE_BYTES = 100 * 1024 * 1024
LARGE_FILE_BYTES = 8 * 1024 * 1024


class CursorPage(list):
    """JSON list plus the X-Next-Cursor header from a paged GET."""

    def __init__(self, items: Sequence[Any], next_cursor: str | None = None) -> None:
        super().__init__(items)
        self.next_cursor = next_cursor


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
                "`dl login --profile claimant` or set DECISIONLAYER_API_KEY."
            )
        self.base_url = base_url.rstrip("/")
        self._last_cursor: str | None = None
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": f"decisionlayer-cli/{__version__}",
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
        headers: Mapping[str, str] | None = None,
        expected: Sequence[int] = (200, 201),
    ) -> Any:
        response = self._client.request(
            method,
            self._url(path),
            params=params,
            json=json,
            data=data,
            files=files,
            headers=headers,
        )
        self._last_cursor = response.headers.get("X-Next-Cursor") or None
        raise_for_status(response, expected=expected)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def _idempotency_headers(self, key: str | None) -> dict[str, str]:
        return {"Idempotency-Key": key or str(uuid.uuid4())}

    def _page(self, data: Any) -> CursorPage:
        items = data if isinstance(data, list) else []
        return CursorPage(items, self._last_cursor)

    def get_me(self) -> dict[str, Any]:
        return self._request("GET", "/me")

    def list_events(
        self,
        *,
        since: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        elif since:
            params["since"] = since
        return self._request("GET", "/events", params=params)

    def create_upload_sessions(self, files: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        payload = {
            "files": [
                {
                    "filename": item["filename"],
                    "size": item["size"],
                    **({"content_type": item["content_type"]} if item.get("content_type") else {}),
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
            timeout=300.0,
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

    def upload_files(self, paths: Sequence[Path]) -> list[str]:
        descriptors = []
        for path in paths:
            if not path.is_file():
                raise ConfigError(f"File not found: {path}")
            size = path.stat().st_size
            if size <= 0:
                raise ConfigError(f"{path} is empty; the upload API requires size > 0.")
            if size > MAX_DIRECT_FILE_BYTES:
                raise ConfigError(f"{path.name} exceeds the 100 MiB per-file limit ({size} bytes).")
            descriptors.append(
                {
                    "path": path,
                    "filename": path.name,
                    "size": size,
                    "content_type": mimetypes.guess_type(path.name)[0],
                }
            )
        batch = self.create_upload_sessions([{k: v for k, v in d.items() if k != "path"} for d in descriptors])
        tickets: list[str] = []
        for session, descriptor in zip(batch["uploads"], descriptors):
            self.put_file(session["upload_url"], descriptor["path"], descriptor["content_type"])
            tickets.append(session["ticket"])
        return tickets

    def _route_files(self, paths: Sequence[Path], *, via_tickets: bool) -> tuple[list[Path], list[str]]:
        """Return multipart paths, or tickets when asked or when any file is 8 MiB or larger.

        One field cannot mix a raw file with a ticket, so a single large file
        sends the whole group through POST /uploads.
        """
        files = [path for path in paths if path is not None]
        if not files:
            return [], []
        for path in files:
            if not path.is_file():
                raise ConfigError(f"File not found: {path}")
        if via_tickets or any(path.stat().st_size >= LARGE_FILE_BYTES for path in files):
            return [], self.upload_files(files)
        return files, []

    def list_consent_cases(
        self,
        *,
        action_required: bool | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        cursor: str | None = None,
    ) -> CursorPage:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        else:
            params["offset"] = offset
        if action_required is not None:
            params["action_required"] = "true" if action_required else "false"
        if status:
            params["status"] = status
        return self._page(self._request("GET", "/consent-cases", params=params))

    def get_consent_case(self, consent_id: str) -> dict[str, Any]:
        return self._request("GET", f"/consent-cases/{consent_id}")

    def create_consent_case(
        self,
        data: Mapping[str, Any],
        *,
        contract_files: Sequence[Path] = (),
        supporting_documents: Sequence[Path] = (),
        via_tickets: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        ticket_groups: dict[str, list[str]] = {}
        file_groups: dict[str, Sequence[Path]] = {}
        contract_paths, contract_tickets = self._route_files(contract_files, via_tickets=via_tickets)
        support_paths, support_tickets = self._route_files(supporting_documents, via_tickets=via_tickets)
        if contract_tickets:
            ticket_groups["contract_files_tickets"] = contract_tickets
        else:
            file_groups["contract_files"] = contract_paths
        if support_tickets:
            ticket_groups["supporting_documents_tickets"] = support_tickets
        else:
            file_groups["supporting_documents"] = support_paths
        form, files = _build_multipart(data, file_groups=file_groups, ticket_groups=ticket_groups)
        try:
            return self._request(
                "POST",
                "/consent-cases",
                files=_as_multipart(form, files),
                headers=self._idempotency_headers(idempotency_key),
            )
        finally:
            _close_files(files)

    def sign_consent_case(self, consent_id: str) -> dict[str, Any]:
        return self._request("POST", f"/consent-cases/{consent_id}/sign")

    def accept_consent_case(self, consent_id: str) -> dict[str, Any]:
        return self._request("POST", f"/consent-cases/{consent_id}/accept")

    def reject_consent_case(self, consent_id: str) -> dict[str, Any]:
        return self._request("POST", f"/consent-cases/{consent_id}/reject")

    def complete_test_consent_respondent(self, consent_id: str) -> dict[str, Any]:
        return self._request("POST", f"/consent-cases/{consent_id}/respondent")

    def list_cases(
        self,
        *,
        action_required: bool | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        cursor: str | None = None,
    ) -> CursorPage:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        else:
            params["offset"] = offset
        if action_required is not None:
            params["action_required"] = "true" if action_required else "false"
        if status:
            params["status"] = status
        return self._page(self._request("GET", "/cases", params=params))

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self._request("GET", f"/cases/{case_id}")

    def claim_case(self, case_id: str, verification_code: str) -> dict[str, Any]:
        return self._request("POST", f"/cases/{case_id}/claim", json={"verification_code": verification_code})

    def sign_case(self, case_id: str) -> dict[str, Any]:
        return self._request("POST", f"/cases/{case_id}/sign")

    def get_decision(self, case_id: str) -> dict[str, Any]:
        return self._request("GET", f"/cases/{case_id}/decision")

    def create_case(
        self,
        data: Mapping[str, Any],
        *,
        contract_file: Path | None = None,
        evidence: Sequence[Path] = (),
        via_tickets: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        ticket_groups: dict[str, list[str]] = {}
        extra_files: list[tuple[str, tuple[str, BinaryIO, str]]] = []
        handles: list[BinaryIO] = []
        file_groups: dict[str, Sequence[Path]] = {}

        contract_paths, contract_tickets = self._route_files(
            [contract_file] if contract_file else [],
            via_tickets=via_tickets,
        )
        if contract_tickets:
            ticket_groups["contract_file_ticket"] = contract_tickets[:1]
        elif contract_paths:
            handle = contract_paths[0].open("rb")
            handles.append(handle)
            extra_files.append(("contract_file", (contract_paths[0].name, handle, _mime(contract_paths[0]))))

        evidence_paths, evidence_tickets = self._route_files(evidence, via_tickets=via_tickets)
        if evidence_tickets:
            ticket_groups["evidence_tickets"] = evidence_tickets
        else:
            file_groups["evidence"] = evidence_paths

        files: list[tuple[str, tuple[str, BinaryIO, str]]] = []
        try:
            form, files = _build_multipart(
                data,
                file_groups=file_groups,
                ticket_groups=ticket_groups,
                extra_files=extra_files,
            )
            return self._request(
                "POST",
                "/cases",
                files=_as_multipart(form, files),
                headers=self._idempotency_headers(idempotency_key),
            )
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
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        groups = {
            "evidence": evidence,
            "evidence_response_files": evidence_response_files,
            "counterclaim_files": counterclaim_files,
        }
        ticket_names = {
            "evidence": "evidence_tickets",
            "evidence_response_files": "evidence_response_files_tickets",
            "counterclaim_files": "counterclaim_files_tickets",
        }
        ticket_groups: dict[str, list[str]] = {}
        file_groups: dict[str, Sequence[Path]] = {}
        for field, paths in groups.items():
            kept, tickets = self._route_files(paths, via_tickets=via_tickets)
            if tickets:
                ticket_groups[ticket_names[field]] = tickets
            elif kept:
                file_groups[field] = kept
        form, files = _build_multipart(data, file_groups=file_groups, ticket_groups=ticket_groups)
        try:
            return self._request(
                "POST",
                f"/cases/{case_id}/responses",
                files=_as_multipart(form, files),
                headers=self._idempotency_headers(idempotency_key),
            )
        finally:
            _close_files(files)

    def create_simulation(
        self,
        data: Mapping[str, Any],
        *,
        contract_file: Path | None = None,
        plaintiff_documents: Sequence[Path] = (),
        respondent_documents: Sequence[Path] = (),
        plaintiff_rebuttal_documents: Sequence[Path] = (),
        respondent_rebuttal_documents: Sequence[Path] = (),
        via_tickets: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        groups = {
            "plaintiff_documents": plaintiff_documents,
            "respondent_documents": respondent_documents,
            "plaintiff_rebuttal_documents": plaintiff_rebuttal_documents,
            "respondent_rebuttal_documents": respondent_rebuttal_documents,
        }
        ticket_groups: dict[str, list[str]] = {}
        file_groups: dict[str, Sequence[Path]] = {}
        extra_files: list[tuple[str, tuple[str, BinaryIO, str]]] = []
        handles: list[BinaryIO] = []
        contract_paths, contract_tickets = self._route_files(
            [contract_file] if contract_file else [],
            via_tickets=via_tickets,
        )
        if contract_tickets:
            ticket_groups["contract_file_ticket"] = contract_tickets[:1]
        elif contract_paths:
            handle = contract_paths[0].open("rb")
            handles.append(handle)
            extra_files.append(("contract_file", (contract_paths[0].name, handle, _mime(contract_paths[0]))))
        for field, paths in groups.items():
            kept, tickets = self._route_files(paths, via_tickets=via_tickets)
            if tickets:
                ticket_groups[f"{field}_tickets"] = tickets
            elif kept:
                file_groups[field] = kept
        files: list[tuple[str, tuple[str, BinaryIO, str]]] = []
        try:
            form, files = _build_multipart(
                data,
                file_groups=file_groups,
                ticket_groups=ticket_groups,
                extra_files=extra_files,
            )
            parts = _as_multipart(form, files)
            if not files and not ticket_groups:
                parts.append(("contract_file", ("", b"", "application/octet-stream")))
            return self._request(
                "POST",
                "/simulations",
                files=parts,
                headers=self._idempotency_headers(idempotency_key),
            )
        finally:
            _close_files(files)
            for handle in handles:
                if not handle.closed:
                    handle.close()

    def get_simulation(self, simulation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/simulations/{simulation_id}")

    def get_simulation_result(self, simulation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/simulations/{simulation_id}/result")


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
