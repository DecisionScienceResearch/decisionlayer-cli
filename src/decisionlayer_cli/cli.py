"""Typer entrypoint and all user-facing commands."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import typer

from decisionlayer_cli import __version__
from decisionlayer_cli.client import DecisionLayerClient
from decisionlayer_cli.config import Settings, config_path, load_settings, save_api_key, save_base_url
from decisionlayer_cli.errors import APIError, ConfigError, DecisionLayerError
from decisionlayer_cli.output import (
    emit,
    render_case,
    render_case_created,
    render_case_list,
    render_consent_created,
    render_consent_list,
    render_error,
    render_response_created,
    render_thread,
    render_uploads,
)

app = typer.Typer(
    name="decisionlayer",
    help="File, track, and respond to DecisionLayer arbitration cases as claimant or respondent.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=False,
)

consent_app = typer.Typer(help="Consent-to-arbitrate requests (POST /api/v1/consent-cases).")
case_app = typer.Typer(help="Contract-clause cases (POST /api/v1/cases).")
response_app = typer.Typer(help="Turn-based filings on a contract-clause case.")
upload_app = typer.Typer(help="Two-step GCS upload tickets.")
flow_app = typer.Typer(help="Guided claimant and respondent walkthroughs.")
config_app = typer.Typer(help="Store API keys and the base URL.")

app.add_typer(consent_app, name="consent")
app.add_typer(case_app, name="case")
app.add_typer(response_app, name="response")
app.add_typer(upload_app, name="upload")
app.add_typer(flow_app, name="flow")
app.add_typer(config_app, name="config")


@dataclass
class Runtime:
    json_mode: bool
    profile: str
    settings: Settings

    def client(self) -> DecisionLayerClient:
        return DecisionLayerClient(self.settings.require_api_key(self.profile), self.settings.base_url)


def _runtime(ctx: typer.Context) -> Runtime:
    obj = ctx.obj
    if not isinstance(obj, Runtime):
        raise ConfigError("Internal error: runtime was not initialized.")
    return obj


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"decisionlayer-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Print raw JSON instead of tables."),
    profile: str = typer.Option(
        "default",
        "--profile",
        "-p",
        help="Which stored/env key to use: default, claimant, or respondent.",
    ),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Bearer token (dvarb_...). Overrides the selected profile."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="API origin. Default: https://www.decisionlayer.ai"),
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."),
) -> None:
    """DecisionLayer arbitration CLI."""
    settings = load_settings(base_url=base_url, api_key=api_key, profile=None if profile == "default" else profile)
    if api_key:
        settings.profiles[profile] = api_key
    ctx.obj = Runtime(json_mode=json_output, profile=profile, settings=settings)


def _run(ctx: typer.Context, fn: Any) -> None:
    runtime = _runtime(ctx)
    try:
        fn(runtime)
    except (APIError, ConfigError, DecisionLayerError, FileNotFoundError, OSError) as exc:
        if runtime.json_mode:
            payload = {"error": str(exc)}
            if isinstance(exc, APIError):
                payload = {
                    "error": {
                        "status": exc.status_code,
                        "message": exc.message,
                        "details": exc.details,
                        "hint": exc.hint,
                    }
                }
            typer.echo(json.dumps(payload, indent=2))
        else:
            render_error(exc)
        raise typer.Exit(code=1) from exc


# --- config ---


@config_app.command("show")
def config_show(ctx: typer.Context) -> None:
    """Show the resolved base URL, profile, and whether keys are set (keys are masked)."""

    def work(runtime: Runtime) -> None:
        profiles = {}
        for name in sorted(set(runtime.settings.profiles) | {"default", "claimant", "respondent"}):
            key = runtime.settings.api_key(name)
            profiles[name] = _mask(key) if key else None
        data = {
            "base_url": runtime.settings.base_url,
            "active_profile": runtime.profile,
            "default_profile": runtime.settings.default_profile,
            "config_file": str(config_path()),
            "keys": profiles,
        }
        emit(runtime.json_mode, data, lambda d: _print_kv(d))

    _run(ctx, work)


def _save_key(runtime: Runtime, target: str, key: str, *, check: bool) -> Path:
    if not key.startswith("dvarb_"):
        typer.echo("Warning: DecisionLayer keys normally start with dvarb_.", err=True)
    if check:
        with DecisionLayerClient(key, runtime.settings.base_url) as client:
            client.list_cases(limit=1)
    return save_api_key(target, key, runtime.settings.base_url)


def _login_work(
    ctx: typer.Context,
    profile: Optional[str],
    api_key: Optional[str],
    skip_check: bool,
) -> None:
    def work(runtime: Runtime) -> None:
        target = profile or runtime.profile
        key = api_key or typer.prompt("API key", hide_input=True)
        path = _save_key(runtime, target, key, check=not skip_check)
        emit(
            runtime.json_mode,
            {"saved": str(path), "profile": target},
            lambda d: typer.echo(f"Saved {d['profile']} key to {d['saved']}"),
        )

    _run(ctx, work)


@config_app.command("set-key")
def config_set_key(
    ctx: typer.Context,
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile to save (default, claimant, respondent). Defaults to the global --profile.",
    ),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="If omitted, you will be prompted."),
    skip_check: bool = typer.Option(False, "--skip-check", help="Save without calling GET /api/v1/cases."),
) -> None:
    """Save an API key to the user config file. Same as `dl login`."""
    _login_work(ctx, profile, api_key, skip_check)


@app.command("login")
def login(
    ctx: typer.Context,
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile to save (default, claimant, respondent). Defaults to the global --profile.",
    ),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="If omitted, you will be prompted."),
    skip_check: bool = typer.Option(False, "--skip-check", help="Save without calling GET /api/v1/cases."),
) -> None:
    """Save an API key under a profile. Checks it against GET /api/v1/cases unless --skip-check."""
    _login_work(ctx, profile, api_key, skip_check)


@config_app.command("set-base-url")
def config_set_base_url(
    ctx: typer.Context,
    url: str = typer.Argument(..., help="Origin, e.g. https://www.decisionlayer.ai"),
) -> None:
    """Save the API origin (production or http://localhost:8000)."""

    def work(runtime: Runtime) -> None:
        path = save_base_url(url)
        emit(runtime.json_mode, {"saved": str(path), "base_url": url}, lambda d: typer.echo(f"Saved base URL to {d['saved']}"))

    _run(ctx, work)


# --- consent ---


@consent_app.command("create")
def consent_create(
    ctx: typer.Context,
    question: Optional[str] = typer.Option(None, "--question", help="question_for_arbitration"),
    respondent_first_name: Optional[str] = typer.Option(None, "--respondent-first-name"),
    respondent_email: Optional[str] = typer.Option(None, "--respondent-email"),
    respondent_last_name: str = typer.Option("", "--respondent-last-name"),
    respondent_type: str = typer.Option("individual", "--respondent-type"),
    financial_demand_usd: str = typer.Option("0.00", "--demand", help="financial_demand_usd, e.g. 3500.00"),
    other_relief: str = typer.Option("", "--other-relief"),
    respondent_contact_first_name: str = typer.Option("", "--respondent-contact-first-name"),
    respondent_contact_last_name: str = typer.Option("", "--respondent-contact-last-name"),
    claimant_type: str = typer.Option("individual", "--claimant-type"),
    claimant_first_name: str = typer.Option("", "--claimant-first-name"),
    claimant_last_name: str = typer.Option("", "--claimant-last-name"),
    claimant_email: str = typer.Option("", "--claimant-email"),
    claimant_contact_first_name: str = typer.Option("", "--claimant-contact-first-name"),
    claimant_contact_last_name: str = typer.Option("", "--claimant-contact-last-name"),
    contract: list[Path] = typer.Option([], "--contract", help="Repeatable contract_files."),
    supporting: list[Path] = typer.Option([], "--supporting", help="Repeatable supporting_documents."),
    from_json: Optional[Path] = typer.Option(None, "--from-json", "--from", help="JSON object merged into form fields."),
    via_tickets: bool = typer.Option(False, "--via-tickets", help="Use POST /api/v1/uploads instead of multipart files."),
) -> None:
    """Create a consent case in ready_to_sign, then sign/pay on the web."""

    def work(runtime: Runtime) -> None:
        fields = {
            "question_for_arbitration": question,
            "respondent_first_name": respondent_first_name,
            "respondent_email": respondent_email,
            "respondent_last_name": respondent_last_name,
            "respondent_type": respondent_type,
            "financial_demand_usd": financial_demand_usd,
            "other_relief": other_relief,
            "respondent_contact_first_name": respondent_contact_first_name,
            "respondent_contact_last_name": respondent_contact_last_name,
            "claimant_type": claimant_type,
            "claimant_first_name": claimant_first_name,
            "claimant_last_name": claimant_last_name,
            "claimant_email": claimant_email,
            "claimant_contact_first_name": claimant_contact_first_name,
            "claimant_contact_last_name": claimant_contact_last_name,
        }
        fields.update(_load_json_object(from_json))
        fields = _pick(fields, CONSENT_FIELDS)
        _require_fields(fields, ["question_for_arbitration", "respondent_first_name", "respondent_email"])
        with runtime.client() as client:
            payload = client.create_consent_case(
                fields,
                contract_files=contract,
                supporting_documents=supporting,
                via_tickets=via_tickets,
            )
        emit(runtime.json_mode, payload, render_consent_created)

    _run(ctx, work)


@consent_app.command("list")
def consent_list(ctx: typer.Context) -> None:
    """List consent requests where this key is claimant or named respondent."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            cases = client.list_consent_cases()
        emit(runtime.json_mode, cases, render_consent_list)

    _run(ctx, work)


@consent_app.command("get")
def consent_get(ctx: typer.Context, consent_id: str = typer.Argument(...)) -> None:
    """Find one consent case by id (the API has no retrieve-by-id endpoint)."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            cases = client.list_consent_cases()
        match = next((item for item in cases if str(item.get("id")) == consent_id), None)
        if match is None:
            raise ConfigError(
                f"Consent case {consent_id!r} is not in GET /api/v1/consent-cases for this key. "
                "There is no GET /api/v1/consent-cases/{id}."
            )
        emit(runtime.json_mode, match, lambda c: render_consent_list([c]))

    _run(ctx, work)


# --- cases ---


@case_app.command("create")
def case_create(
    ctx: typer.Context,
    question: Optional[str] = typer.Option(None, "--question"),
    argument: Optional[str] = typer.Option(None, "--argument"),
    respondent_first_name: Optional[str] = typer.Option(None, "--respondent-first-name"),
    respondent_email: Optional[str] = typer.Option(None, "--respondent-email"),
    respondent_last_name: str = typer.Option("", "--respondent-last-name"),
    respondent_type: str = typer.Option("individual", "--respondent-type"),
    financial_demand_usd: str = typer.Option("0.00", "--demand"),
    other_relief: str = typer.Option("", "--other-relief"),
    evidence_demands: str = typer.Option("", "--evidence-demands"),
    contract: Optional[Path] = typer.Option(None, "--contract", help="Governing contract_file (pdf/docx/rtf/txt)."),
    evidence: list[Path] = typer.Option([], "--evidence", help="Repeatable opening evidence files."),
    arbitration_contract_description: str = typer.Option("", "--arbitration-contract-description"),
    respondent_street_address: str = typer.Option("", "--respondent-street"),
    respondent_street_address_2: str = typer.Option("", "--respondent-street-2"),
    respondent_city: str = typer.Option("", "--respondent-city"),
    respondent_state: str = typer.Option("", "--respondent-state"),
    respondent_zipcode: str = typer.Option("", "--respondent-zip"),
    claimant_street_address: str = typer.Option("", "--claimant-street"),
    claimant_street_address_2: str = typer.Option("", "--claimant-street-2"),
    claimant_city: str = typer.Option("", "--claimant-city"),
    claimant_state: str = typer.Option("", "--claimant-state"),
    claimant_zipcode: str = typer.Option("", "--claimant-zip"),
    filing_capacity: str = typer.Option("personal", "--filing-capacity", help="personal | organization | attorney"),
    claimant_legal_name: str = typer.Option("", "--claimant-legal-name"),
    relationship_to_claimant: str = typer.Option("", "--relationship-to-claimant"),
    first_name: str = typer.Option("", "--first-name"),
    last_name: str = typer.Option("", "--last-name"),
    email_address: str = typer.Option("", "--email"),
    street_address: str = typer.Option("", "--street"),
    street_address_2: str = typer.Option("", "--street-2"),
    city: str = typer.Option("", "--city"),
    state: str = typer.Option("", "--state"),
    zipcode: str = typer.Option("", "--zip"),
    title: str = typer.Option("", "--title"),
    claimant_affirmation: str = typer.Option("true", "--affirmation", help="Must be true to file."),
    from_json: Optional[Path] = typer.Option(None, "--from-json", "--from", help="JSON object merged into form fields."),
    via_tickets: bool = typer.Option(False, "--via-tickets"),
) -> None:
    """File a contract-clause case. Lands in awaiting_signature; finish on action_url."""

    def work(runtime: Runtime) -> None:
        fields = {
            "question_for_arbitration": question,
            "argument": argument,
            "respondent_first_name": respondent_first_name,
            "respondent_email": respondent_email,
            "respondent_last_name": respondent_last_name,
            "respondent_type": respondent_type,
            "financial_demand_usd": financial_demand_usd,
            "other_relief": other_relief,
            "evidence_demands": evidence_demands,
            "arbitration_contract_description": arbitration_contract_description,
            "respondent_street_address": respondent_street_address,
            "respondent_street_address_2": respondent_street_address_2,
            "respondent_city": respondent_city,
            "respondent_state": respondent_state,
            "respondent_zipcode": respondent_zipcode,
            "claimant_street_address": claimant_street_address,
            "claimant_street_address_2": claimant_street_address_2,
            "claimant_city": claimant_city,
            "claimant_state": claimant_state,
            "claimant_zipcode": claimant_zipcode,
            "filing_capacity": filing_capacity,
            "claimant_legal_name": claimant_legal_name,
            "relationship_to_claimant": relationship_to_claimant,
            "first_name": first_name,
            "last_name": last_name,
            "email_address": email_address,
            "street_address": street_address,
            "street_address_2": street_address_2,
            "city": city,
            "state": state,
            "zipcode": zipcode,
            "title": title,
            "claimant_affirmation": claimant_affirmation,
        }
        fields.update(_load_json_object(from_json))
        fields = _pick(fields, CASE_FIELDS)
        _require_fields(fields, ["question_for_arbitration", "argument", "respondent_first_name", "respondent_email"])
        if contract is None and not via_tickets:
            raise ConfigError(
                "Attach the governing contract with --contract (pdf/docx/rtf/txt), "
                "or pass --via-tickets after uploading it."
            )
        with runtime.client() as client:
            payload = client.create_case(
                fields,
                contract_file=contract,
                evidence=evidence,
                via_tickets=via_tickets,
            )
        emit(runtime.json_mode, payload, render_case_created)

    _run(ctx, work)


@case_app.command("list")
def case_list(
    ctx: typer.Context,
    action_required: bool = typer.Option(False, "--action-required", help="Only cases waiting on this key."),
    status: Optional[str] = typer.Option(None, "--status", help="draft, awaiting_signature, awaiting_payment, ..."),
    limit: int = typer.Option(50, "--limit", min=1, max=200),
    offset: int = typer.Option(0, "--offset", min=0),
) -> None:
    """List contract-clause cases this key is a party to (newest first)."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            cases = client.list_cases(
                action_required=True if action_required else None,
                status=status,
                limit=limit,
                offset=offset,
            )
        emit(runtime.json_mode, cases, render_case_list)

    _run(ctx, work)


@case_app.command("get")
def case_get(ctx: typer.Context, case_id: str = typer.Argument(...)) -> None:
    """Fetch one case, including status, current_turn, next_action, and action_url."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            case = client.get_case(case_id)
        emit(runtime.json_mode, case, render_case)

    _run(ctx, work)


@case_app.command("inbox")
def case_inbox(ctx: typer.Context) -> None:
    """Shortcut for cases waiting on this key."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            cases = client.list_cases(action_required=True)
        emit(runtime.json_mode, cases, render_case_list)

    _run(ctx, work)


@case_app.command("watch")
def case_watch(
    ctx: typer.Context,
    case_id: str = typer.Argument(...),
    interval: float = typer.Option(5.0, "--interval", help="Seconds between polls."),
    until: Optional[str] = typer.Option(None, "--until", help="Stop when status matches, e.g. awaiting_response or decided."),
    until_action: bool = typer.Option(False, "--until-action", help="Stop when action_required is true."),
    max_polls: int = typer.Option(60, "--max-polls"),
) -> None:
    """Poll GET /api/v1/cases/{id} until a status or action appears."""

    def work(runtime: Runtime) -> None:
        last: dict[str, Any] | None = None
        with runtime.client() as client:
            for _ in range(max_polls):
                case = client.get_case(case_id)
                last = case
                if not runtime.json_mode:
                    typer.echo(f"{case.get('status')} turn={case.get('current_turn')} next={case.get('next_action')}")
                if until and case.get("status") == until:
                    break
                if until_action and case.get("action_required"):
                    break
                if not until and not until_action and case.get("status") == "decided":
                    break
                time.sleep(interval)
            else:
                if last is not None and not runtime.json_mode:
                    typer.echo("Still in progress. Re-run watch, or open view_url / action_url.")
        if last is not None:
            emit(runtime.json_mode, last, render_case)

    _run(ctx, work)


@case_app.command("open")
def case_open(
    ctx: typer.Context,
    case_id: str = typer.Argument(...),
    view: bool = typer.Option(False, "--view", help="Open view_url instead of action_url."),
) -> None:
    """Open the web page for the next action (or the case view)."""

    def work(runtime: Runtime) -> None:
        import webbrowser

        with runtime.client() as client:
            case = client.get_case(case_id)
        url = case.get("view_url") if view else (case.get("action_url") or case.get("view_url"))
        if not url:
            raise ConfigError("No action_url or view_url on this case.")
        webbrowser.open(str(url))
        emit(runtime.json_mode, {"url": url, "next_action": case.get("next_action")}, lambda d: typer.echo(d["url"]))

    _run(ctx, work)


# --- responses ---


@response_app.command("list")
def response_list(ctx: typer.Context, case_id: str = typer.Argument(...)) -> None:
    """Print the submitted response thread, oldest first."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            thread = client.list_responses(case_id)
        emit(runtime.json_mode, thread, render_thread)

    _run(ctx, work)


@response_app.command("submit")
def response_submit(
    ctx: typer.Context,
    case_id: str = typer.Argument(...),
    argument: str = typer.Option(..., "--argument"),
    affirmation: str = typer.Option("true", "--affirmation"),
    evidence: list[Path] = typer.Option([], "--evidence"),
    evidence_response: Optional[str] = typer.Option(None, "--evidence-response", help="Rounds 1–2."),
    evidence_response_file: list[Path] = typer.Option([], "--evidence-response-file"),
    evidence_demands: Optional[str] = typer.Option(None, "--evidence-demands", help="Round 1 only."),
    counterclaim_argument: Optional[str] = typer.Option(None, "--counterclaim-argument", help="Round 1 only."),
    counterclaim_amount_usd: Optional[str] = typer.Option(None, "--counterclaim-amount"),
    counterclaim_other_relief: Optional[str] = typer.Option(None, "--counterclaim-other-relief"),
    counterclaim_file: list[Path] = typer.Option([], "--counterclaim-file"),
    via_tickets: bool = typer.Option(False, "--via-tickets"),
) -> None:
    """Submit the current turn. The server infers the round from case state."""

    def work(runtime: Runtime) -> None:
        fields: dict[str, Any] = {"argument": argument, "affirmation": affirmation}
        if evidence_response is not None:
            fields["evidence_response"] = evidence_response
        if evidence_demands is not None:
            fields["evidence_demands"] = evidence_demands
        if counterclaim_argument is not None:
            fields["counterclaim_argument"] = counterclaim_argument
        if counterclaim_amount_usd is not None:
            fields["counterclaim_amount_usd"] = counterclaim_amount_usd
        if counterclaim_other_relief is not None:
            fields["counterclaim_other_relief"] = counterclaim_other_relief
        with runtime.client() as client:
            payload = client.create_response(
                case_id,
                fields,
                evidence=evidence,
                evidence_response_files=evidence_response_file,
                counterclaim_files=counterclaim_file,
                via_tickets=via_tickets,
            )
        emit(runtime.json_mode, payload, render_response_created)

    _run(ctx, work)


# --- uploads ---


@upload_app.command("sessions")
def upload_sessions(
    ctx: typer.Context,
    files: list[Path] = typer.Argument(..., help="Local files to describe."),
    role: Optional[str] = typer.Option(None, "--role", help="Optional role copied onto each descriptor."),
) -> None:
    """Create resumable upload sessions, PUT each file, and print tickets."""

    def work(runtime: Runtime) -> None:
        descriptors = []
        for path in files:
            if not path.is_file():
                raise FileNotFoundError(path)
            item = {
                "filename": path.name,
                "size": path.stat().st_size,
                "content_type": _guess_type(path),
            }
            if role:
                item["role"] = role
            descriptors.append(item)
        with runtime.client() as client:
            payload = client.create_upload_sessions(descriptors)
            for session, path in zip(payload["uploads"], files):
                client.put_file(session["upload_url"], path, session.get("content_type"))
        if not runtime.json_mode:
            typer.echo("PUT finished for every file. Pass the tickets on create/submit, or use --via-tickets.")
        emit(runtime.json_mode, payload, render_uploads)

    _run(ctx, work)


@upload_app.command("cancel")
def upload_cancel(
    ctx: typer.Context,
    tickets: list[str] = typer.Argument(..., help="Tickets to delete."),
) -> None:
    """Cancel unused upload tickets owned by this key."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            payload = client.cancel_upload_sessions(tickets)
        emit(runtime.json_mode, payload, lambda d: typer.echo(f"Deleted {d.get('deleted')} temporary object(s)."))

    _run(ctx, work)


# --- guided flows ---


@flow_app.command("claimant")
def flow_claimant(
    ctx: typer.Context,
    kind: str = typer.Option("case", "--kind", help="consent or case"),
    from_json: Path = typer.Option(Path("examples/sample_case.json"), "--from-json"),
    contract: Path = typer.Option(Path("examples/sample_contract.txt"), "--contract"),
    evidence: Path = typer.Option(Path("examples/sample_evidence.txt"), "--evidence"),
) -> None:
    """Create the sample claimant filing, then print the web steps the API cannot do."""

    def work(runtime: Runtime) -> None:
        fields = _load_json_object(from_json)
        email = str(fields.get("respondent_email") or "")
        if "REPLACE" in email:
            typer.echo(
                "Warning: replace respondent_email in the JSON with an inbox the respondent account can receive.",
                err=True,
            )
        with runtime.client() as client:
            if kind == "consent":
                payload = client.create_consent_case(
                    _pick(
                        {
                            "question_for_arbitration": fields.get("question_for_arbitration"),
                            "financial_demand_usd": fields.get("financial_demand_usd", "0.00"),
                            "other_relief": fields.get("other_relief", ""),
                            "respondent_first_name": fields.get("respondent_first_name"),
                            "respondent_last_name": fields.get("respondent_last_name", ""),
                            "respondent_email": fields.get("respondent_email"),
                        },
                        CONSENT_FIELDS,
                    ),
                    contract_files=[contract] if contract.is_file() else [],
                )
                emit(runtime.json_mode, payload, render_consent_created)
                if not runtime.json_mode:
                    typer.echo("\nNext: open sign_url, sign, pay the consent letter + filing fee on the dashboard.")
                    typer.echo("The respondent is notified only after those web steps complete.")
                return
            if kind != "case":
                raise ConfigError("--kind must be consent or case")
            payload = client.create_case(
                {
                    **_pick({k: v for k, v in fields.items() if v is not None}, CASE_FIELDS),
                    "claimant_affirmation": fields.get("claimant_affirmation") or "true",
                },
                contract_file=contract if contract.is_file() else None,
                evidence=[evidence] if evidence.is_file() else (),
            )
            emit(runtime.json_mode, payload, render_case_created)
            if not runtime.json_mode:
                typer.echo("\nNext web steps for the claimant (not API calls):")
                typer.echo("  1. sign_terms")
                typer.echo("  2. pay_filing_fee")
                typer.echo("  3. verify_identity")
                typer.echo("Then wait for the respondent to claim the case, sign terms, and file round 1.")
                case = payload.get("case") or {}
                if case.get("id"):
                    typer.echo(f"\nTrack with:\n  dl --profile claimant case watch {case['id']} --until awaiting_response")

    _run(ctx, work)


@flow_app.command("respondent")
def flow_respondent(
    ctx: typer.Context,
    case_id: str = typer.Argument(...),
    argument: Optional[str] = typer.Option(None, "--argument"),
    evidence: list[Path] = typer.Option([], "--evidence"),
    evidence_response: Optional[str] = typer.Option(None, "--evidence-response"),
    evidence_response_file: list[Path] = typer.Option([], "--evidence-response-file"),
    evidence_demands: Optional[str] = typer.Option(None, "--evidence-demands"),
    counterclaim_argument: Optional[str] = typer.Option(None, "--counterclaim-argument"),
    counterclaim_amount_usd: Optional[str] = typer.Option(None, "--counterclaim-amount"),
    from_json: Optional[Path] = typer.Option(None, "--from-json", help="e.g. examples/sample_respondent_round1.json"),
    wait_for_web: bool = typer.Option(True, "--wait-for-web/--no-wait-for-web"),
) -> None:
    """Load a claimed case as respondent, block on web sign/KYC if needed, then submit this turn."""

    def work(runtime: Runtime) -> None:
        extra = _load_json_object(from_json)
        resolved_argument = argument or extra.get("argument")
        if not resolved_argument:
            raise ConfigError("Provide --argument or --from-json with an 'argument' field.")
        with runtime.client() as client:
            case = client.get_case(case_id)
            if case.get("role") != "respondent" and not runtime.json_mode:
                typer.echo(
                    f"Warning: this key's role on the case is {case.get('role')!r}, not respondent. "
                    "Use --profile respondent with the respondent's API key.",
                    err=True,
                )
            emit(runtime.json_mode, case, render_case)
            while wait_for_web and case.get("next_action") in {"sign_terms", "pay_filing_fee", "verify_identity", "complete_form"}:
                if runtime.json_mode:
                    break
                typer.echo()
                typer.echo(f"Complete {case.get('next_action')} at:\n{case.get('action_url') or case.get('view_url')}")
                typer.prompt("Press Enter after finishing that web step", default="", show_default=False)
                case = client.get_case(case_id)
                emit(False, case, render_case)
            if case.get("status") != "awaiting_response" or case.get("current_turn") != case.get("role"):
                raise ConfigError(
                    f"Not ready to submit. status={case.get('status')} current_turn={case.get('current_turn')} "
                    f"role={case.get('role')} next_action={case.get('next_action')}"
                )
            fields: dict[str, Any] = {"argument": resolved_argument, "affirmation": extra.get("affirmation") or "true"}
            resolved_evidence_response = evidence_response if evidence_response is not None else extra.get("evidence_response")
            resolved_demands = evidence_demands if evidence_demands is not None else extra.get("evidence_demands")
            resolved_counterclaim = counterclaim_argument if counterclaim_argument is not None else extra.get("counterclaim_argument")
            resolved_amount = counterclaim_amount_usd if counterclaim_amount_usd is not None else extra.get("counterclaim_amount_usd")
            if resolved_evidence_response is not None:
                fields["evidence_response"] = resolved_evidence_response
            if resolved_demands is not None:
                fields["evidence_demands"] = resolved_demands
            if resolved_counterclaim is not None:
                fields["counterclaim_argument"] = resolved_counterclaim
            if resolved_amount is not None:
                fields["counterclaim_amount_usd"] = resolved_amount
            payload = client.create_response(
                case_id,
                fields,
                evidence=evidence,
                evidence_response_files=evidence_response_file,
            )
        emit(runtime.json_mode, payload, render_response_created)

    _run(ctx, work)


@flow_app.command("status")
def flow_status(ctx: typer.Context, case_id: str = typer.Argument(...)) -> None:
    """Show the case plus the response thread for the active profile."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            case = client.get_case(case_id)
            thread = client.list_responses(case_id)
        if runtime.json_mode:
            typer.echo(json.dumps({"case": case, "responses": thread}, indent=2, default=str))
            return
        render_case(case)
        typer.echo()
        render_thread(thread)

    _run(ctx, work)


def _require_fields(fields: dict[str, Any], names: list[str]) -> None:
    missing = [name for name in names if not fields.get(name)]
    if missing:
        raise ConfigError("Missing required fields: " + ", ".join(missing))


def _pick(fields: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if key in allowed and value not in (None, "")}


CONSENT_FIELDS = {
    "question_for_arbitration",
    "financial_demand_usd",
    "other_relief",
    "respondent_type",
    "respondent_first_name",
    "respondent_last_name",
    "respondent_email",
    "respondent_contact_first_name",
    "respondent_contact_last_name",
    "claimant_type",
    "claimant_first_name",
    "claimant_last_name",
    "claimant_email",
    "claimant_contact_first_name",
    "claimant_contact_last_name",
}

CASE_FIELDS = {
    "question_for_arbitration",
    "argument",
    "financial_demand_usd",
    "other_relief",
    "evidence_demands",
    "arbitration_contract_description",
    "respondent_type",
    "respondent_first_name",
    "respondent_last_name",
    "respondent_email",
    "respondent_street_address",
    "respondent_street_address_2",
    "respondent_city",
    "respondent_state",
    "respondent_zipcode",
    "filing_capacity",
    "claimant_legal_name",
    "relationship_to_claimant",
    "claimant_street_address",
    "claimant_street_address_2",
    "claimant_city",
    "claimant_state",
    "claimant_zipcode",
    "first_name",
    "last_name",
    "email_address",
    "street_address",
    "street_address_2",
    "city",
    "state",
    "zipcode",
    "title",
    "claimant_affirmation",
}


def _load_json_object(path: Optional[Path]) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.is_file():
        raise ConfigError(f"JSON file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object")
    return {str(key): value for key, value in data.items()}


def _mask(key: str) -> str:
    if len(key) <= 10:
        return "dvarb_***"
    return key[:8] + "…" + key[-4:]


def _print_kv(data: dict[str, Any]) -> None:
    for key, value in data.items():
        typer.echo(f"{key}: {json.dumps(value) if isinstance(value, (dict, list)) else value}")


def _guess_type(path: Path) -> str:
    import mimetypes

    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"