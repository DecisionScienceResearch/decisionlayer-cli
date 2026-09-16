"""Human-readable tables for CLI output."""

from __future__ import annotations

import json
from typing import Any, Callable

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def emit(json_mode: bool, data: Any, render: Callable[[Any], None] | None = None) -> None:
    if json_mode:
        typer.echo(json.dumps(data, indent=2, default=str))
        return
    if render is None:
        typer.echo(json.dumps(data, indent=2, default=str))
        return
    render(data)


def render_error(exc: BaseException) -> None:
    from decisionlayer_cli.errors import APIError

    if isinstance(exc, APIError):
        console.print(f"[bold red]HTTP {exc.status_code}[/] {exc.message}")
        for detail in exc.details:
            console.print(f"  • {detail}")
        if exc.hint:
            console.print()
            console.print(Panel(exc.hint, title="What to do", border_style="yellow"))
        return
    console.print(f"[bold red]{exc}[/]")


def render_consent_created(payload: dict[str, Any]) -> None:
    case = payload.get("case") or payload
    _consent_table([case], title="Consent case created")
    sign_url = payload.get("sign_url") or case.get("sign_url")
    dashboard = payload.get("dashboard_url")
    if sign_url or dashboard:
        lines = []
        if sign_url:
            lines.append(f"Sign and pay on the web:\n{sign_url}")
        if dashboard:
            lines.append(f"Dashboard:\n{dashboard}")
        console.print(Panel("\n\n".join(lines), title="Web steps (not in the API)", border_style="cyan"))


def render_consent_list(cases: list[dict[str, Any]]) -> None:
    if not cases:
        console.print("No consent cases for this API key.")
        return
    _consent_table(cases, title=f"Consent cases ({len(cases)})")


def _consent_table(cases: list[dict[str, Any]], title: str) -> None:
    table = Table(title=title, show_lines=False)
    table.add_column("ID")
    table.add_column("Status")
    table.add_column("Respondent")
    table.add_column("Demand")
    table.add_column("Question")
    for case in cases:
        table.add_row(
            str(case.get("id") or ""),
            str(case.get("status") or ""),
            _person(case.get("respondent_first_name"), case.get("respondent_last_name"), case.get("respondent_email")),
            str(case.get("financial_demand_usd") or ""),
            _clip(case.get("question_for_arbitration"), 60),
        )
    console.print(table)


def render_case_created(payload: dict[str, Any]) -> None:
    case = payload.get("case") or payload
    render_case(case)
    action_url = payload.get("action_url") or case.get("action_url")
    message = payload.get("message")
    lines = []
    if message:
        lines.append(str(message))
    if action_url:
        lines.append(f"Finish signing, payment, and identity on the web:\n{action_url}")
    dashboard = payload.get("dashboard_url")
    if dashboard:
        lines.append(f"Dashboard:\n{dashboard}")
    if lines:
        console.print(Panel("\n\n".join(lines), title="Web steps (not in the API)", border_style="cyan"))


def render_case(case: dict[str, Any]) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Field", style="bold")
    table.add_column("Value")
    rows = [
        ("ID", case.get("id")),
        ("Status", case.get("status")),
        ("Your role", case.get("role")),
        ("Current turn", case.get("current_turn")),
        ("Action required", case.get("action_required")),
        ("Next action", case.get("next_action")),
        ("Demand", case.get("financial_demand_usd")),
        ("Question", case.get("question_for_arbitration")),
        ("Respondent", _person(case.get("respondent_first_name"), case.get("respondent_last_name"), case.get("respondent_email"))),
        ("Claimant email", case.get("claimant_email")),
        ("Action URL", case.get("action_url")),
        ("View URL", case.get("view_url")),
        ("Updated", case.get("updated_at")),
    ]
    for label, value in rows:
        if value is None or value == "":
            continue
        table.add_row(label, str(value))
    console.print(table)
    if case.get("action_required") and case.get("next_action"):
        console.print(
            Panel(
                f"This key must [bold]{case['next_action']}[/]\n{case.get('action_url') or case.get('view_url') or ''}",
                title="Waiting on you",
                border_style="yellow",
            )
        )
    if case.get("status") == "decided" and case.get("view_url"):
        console.print(
            Panel(
                f"There is no decision JSON endpoint. Open:\n{case['view_url']}",
                title="Decision ready",
                border_style="green",
            )
        )


def render_case_list(cases: list[dict[str, Any]]) -> None:
    if not cases:
        console.print("No cases for this API key.")
        return
    table = Table(title=f"Cases ({len(cases)})")
    table.add_column("ID")
    table.add_column("Status")
    table.add_column("Role")
    table.add_column("Turn")
    table.add_column("Next")
    table.add_column("Question")
    for case in cases:
        next_action = case.get("next_action") or ""
        if case.get("action_required"):
            next_cell = Text(str(next_action), style="bold yellow")
        else:
            next_cell = Text(str(next_action))
        table.add_row(
            str(case.get("id") or ""),
            str(case.get("status") or ""),
            str(case.get("role") or ""),
            str(case.get("current_turn") or ""),
            next_cell,
            _clip(case.get("question_for_arbitration"), 50),
        )
    console.print(table)


def render_thread(entries: list[dict[str, Any]]) -> None:
    if not entries:
        console.print("No submitted rounds yet (web drafts are not returned by the API).")
        return
    table = Table(title=f"Response thread ({len(entries)} round(s), oldest first)")
    table.add_column("Round", justify="right")
    table.add_column("By")
    table.add_column("Submitted")
    table.add_column("Due next")
    table.add_column("Argument")
    table.add_column("Files")
    for entry in entries:
        files = entry.get("evidence_files") or []
        names = ", ".join(
            f"{item.get('kind')}:{item.get('name')}" if isinstance(item, dict) else str(item)
            for item in files
        ) or "—"
        table.add_row(
            str(entry.get("round") or ""),
            str(entry.get("submitted_by") or ""),
            str(entry.get("submitted_at") or ""),
            str(entry.get("due_at") or "—"),
            _clip(entry.get("argument"), 70),
            _clip(names, 40),
        )
    console.print(table)


def render_response_created(payload: dict[str, Any]) -> None:
    submitted = payload.get("response") or {}
    console.print(
        Panel(
            f"Round {submitted.get('round')} submitted by the {submitted.get('submitted_by')}.",
            title="Response recorded",
            border_style="green",
        )
    )
    if payload.get("case"):
        render_case(payload["case"])


def render_uploads(payload: dict[str, Any]) -> None:
    table = Table(title=f"Upload sessions (batch {payload.get('batch_id') or ''})")
    table.add_column("File")
    table.add_column("Size")
    table.add_column("Ticket")
    table.add_column("Expires")
    table.add_column("Role")
    for item in payload.get("uploads") or []:
        table.add_row(
            str(item.get("filename") or ""),
            str(item.get("size") or ""),
            _clip(item.get("ticket"), 24),
            str(item.get("expires_at") or ""),
            str(item.get("role") or ""),
        )
    console.print(table)
    console.print("PUT of each file to upload_url is already done. Submit these tickets on create/respond.")


def _person(first: Any, last: Any, email: Any) -> str:
    name = " ".join(part for part in (first, last) if part).strip()
    if name and email:
        return f"{name} <{email}>"
    return str(name or email or "")


def _clip(value: Any, width: int) -> str:
    text = "" if value is None else str(value).replace("\n", " ")
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"