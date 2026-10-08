"""Archwares™ command-line client for the DecisionLayer API."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

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
    render_consent,
    render_consent_created,
    render_consent_list,
    render_decision,
    render_error,
    render_events,
    render_me,
    render_page_cursor,
    render_response_created,
    render_signing,
    render_feedback,
    render_simulation,
    render_simulation_list,
    render_thread,
    render_uploads,
)

app = typer.Typer(
    name="decisionlayer",
    help="Archwares™ client. File, track, and respond to DecisionLayer arbitration cases as claimant or respondent.",
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
simulation_app = typer.Typer(help="One-shot simulations. Requires a production API key, not a test key.")

app.add_typer(consent_app, name="consent")
app.add_typer(case_app, name="case")
app.add_typer(response_app, name="response")
app.add_typer(upload_app, name="upload")
app.add_typer(flow_app, name="flow")
app.add_typer(config_app, name="config")
app.add_typer(simulation_app, name="simulation")


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
        typer.echo(f"decisionlayer-cli {__version__}  ·  Archwares™")
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
                        "reason": exc.reason or None,
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


@app.command("whoami")
def whoami(ctx: typer.Context) -> None:
    """Show the account behind the active API key (GET /api/v1/me)."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            principal = client.get_me()
        emit(runtime.json_mode, principal, render_me)

    _run(ctx, work)


@app.command("feedback")
def feedback(
    ctx: typer.Context,
    message: str = typer.Argument(..., help="What failed, what was confusing, or what would help."),
    category: str = typer.Option("other", "--category", help="bug, idea, praise, or other."),
    case_id: Optional[str] = typer.Option(None, "--case-id", help="A case_ or creq_ id this note is about."),
) -> None:
    """Send a note to the DecisionLayer team (POST /api/v1/feedback)."""

    def work(runtime: Runtime) -> None:
        if category not in {"bug", "idea", "praise", "other"}:
            raise ConfigError("--category must be bug, idea, praise, or other.")
        with runtime.client() as client:
            payload = client.send_feedback(message, category=category, case_id=case_id)
        emit(runtime.json_mode, payload, render_feedback)

    _run(ctx, work)


@app.command("events")
def events(
    ctx: typer.Context,
    since: Optional[str] = typer.Option(None, "--since", help="ISO time. Ignored when --cursor is set."),
    cursor: Optional[str] = typer.Option(None, "--cursor", help="next_cursor from the previous page."),
    limit: int = typer.Option(50, "--limit", min=1, max=200),
) -> None:
    """Poll the change feed (GET /api/v1/events) instead of every case."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            payload = client.list_events(since=since, cursor=cursor, limit=limit)
        emit(runtime.json_mode, payload, render_events)

    _run(ctx, work)


@config_app.command("set-base-url")
def config_set_base_url(
    ctx: typer.Context,
    url: str = typer.Argument(..., help="Origin, e.g. https://www.decisionlayer.ai"),
) -> None:
    """Save the API origin. Production is https://www.decisionlayer.ai. Staging is https://staging.decisionlayer.ai."""

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
    idempotency_key: Optional[str] = typer.Option(None, "--idempotency-key", help="Reuse this token to replay the same create. A new token is used when omitted."),
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
        _require_fields(fields, _consent_required(fields))
        with runtime.client() as client:
            payload = client.create_consent_case(
                fields,
                contract_files=contract,
                supporting_documents=supporting,
                via_tickets=via_tickets,
                idempotency_key=idempotency_key,
            )
        emit(runtime.json_mode, payload, render_consent_created)

    _run(ctx, work)


@consent_app.command("list")
def consent_list(
    ctx: typer.Context,
    action_required: bool = typer.Option(False, "--action-required", help="Only consent requests waiting on this key."),
    status: Optional[str] = typer.Option(None, "--status"),
    limit: int = typer.Option(50, "--limit", min=1, max=200),
    offset: int = typer.Option(0, "--offset", min=0),
    cursor: Optional[str] = typer.Option(None, "--cursor", help="X-Next-Cursor from the previous page."),
) -> None:
    """List consent requests where this key is claimant or named respondent."""

    def work(runtime: Runtime) -> None:
        _reject_cursor_offset(cursor, offset)
        with runtime.client() as client:
            cases = client.list_consent_cases(
                action_required=True if action_required else None,
                status=status,
                limit=limit,
                offset=offset,
                cursor=cursor,
            )
        _emit_page(runtime, cases, "consent_cases", render_consent_list)

    _run(ctx, work)


@consent_app.command("get")
def consent_get(ctx: typer.Context, consent_id: str = typer.Argument(...)) -> None:
    """Fetch one consent case by id."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            case = client.get_consent_case(consent_id)
        emit(runtime.json_mode, case, render_consent)

    _run(ctx, work)


@consent_app.command("sign")
def consent_sign(
    ctx: typer.Context,
    consent_id: str = typer.Argument(...),
    open_browser: bool = typer.Option(False, "--open", help="Open the signing URL in a browser."),
) -> None:
    """Return a signing URL when next_action is sign_terms."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            session = client.sign_consent_case(consent_id)
        _maybe_open(open_browser, session.get("signing_url"))
        emit(runtime.json_mode, session, render_signing)

    _run(ctx, work)


@consent_app.command("accept")
def consent_accept(ctx: typer.Context, consent_id: str = typer.Argument(...)) -> None:
    """Accept a consent case as the named respondent."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            case = client.accept_consent_case(consent_id)
        emit(runtime.json_mode, case, render_consent)

    _run(ctx, work)


@consent_app.command("reject")
def consent_reject(
    ctx: typer.Context,
    consent_id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Required. Reject is terminal and emails the claimant."),
) -> None:
    """Reject a consent case. This ends the request and emails the claimant."""

    def work(runtime: Runtime) -> None:
        if not yes:
            raise ConfigError("Reject is terminal. Re-run with --yes to email the claimant and close the request.")
        with runtime.client() as client:
            case = client.reject_consent_case(consent_id)
        emit(runtime.json_mode, case, render_consent)

    _run(ctx, work)


@consent_app.command("claim")
def consent_claim(
    ctx: typer.Context,
    token: str = typer.Option(..., "--token", help="Last path segment of the /consent/respondent/{token} invitation link."),
) -> None:
    """Bind a live consent request to this account with the emailed invitation token."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            case = client.claim_consent_case(token.strip())
        emit(runtime.json_mode, case, render_consent)

    _run(ctx, work)


@consent_app.command("complete-respondent")
def consent_complete_respondent(ctx: typer.Context, consent_id: str = typer.Argument(...)) -> None:
    """Test keys only: claim, accept, and sign in one call. The key email must match respondent_email."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            case = client.complete_test_consent_respondent(consent_id)
        emit(runtime.json_mode, case, render_consent)

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
    idempotency_key: Optional[str] = typer.Option(None, "--idempotency-key", help="Reuse this token to replay the same create."),
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
        _require_fields(
            fields,
            [
                "question_for_arbitration",
                "argument",
                "respondent_first_name",
                "respondent_email",
                "respondent_street_address",
                "respondent_city",
                "respondent_state",
                "respondent_zipcode",
                "claimant_street_address",
                "claimant_city",
                "claimant_state",
                "claimant_zipcode",
            ],
        )
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
                idempotency_key=idempotency_key,
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
    cursor: Optional[str] = typer.Option(None, "--cursor", help="X-Next-Cursor from the previous page."),
) -> None:
    """List contract-clause cases this key is a party to (newest first). Simulations are excluded."""

    def work(runtime: Runtime) -> None:
        _reject_cursor_offset(cursor, offset)
        with runtime.client() as client:
            cases = client.list_cases(
                action_required=True if action_required else None,
                status=status,
                limit=limit,
                offset=offset,
                cursor=cursor,
            )
        _emit_page(runtime, cases, "cases", render_case_list)

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
        _emit_page(runtime, cases, "cases", render_case_list)

    _run(ctx, work)


@case_app.command("claim")
def case_claim(
    ctx: typer.Context,
    case_id: str = typer.Argument(...),
    code: str = typer.Option(..., "--code", help="Verification code from the respondent notice. 1-32 characters."),
) -> None:
    """Claim a case as the respondent (POST /api/v1/cases/{id}/claim)."""

    def work(runtime: Runtime) -> None:
        if not code.strip() or len(code.strip()) > 32:
            raise ConfigError("The verification code must be 1-32 characters.")
        with runtime.client() as client:
            case = client.claim_case(case_id, code.strip())
        emit(runtime.json_mode, case, render_case)

    _run(ctx, work)


@case_app.command("sign")
def case_sign(
    ctx: typer.Context,
    case_id: str = typer.Argument(...),
    open_browser: bool = typer.Option(False, "--open", help="Open the signing URL in a browser."),
) -> None:
    """Return a signing URL for the party whose next action is sign_terms."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            session = client.sign_case(case_id)
        _maybe_open(open_browser, session.get("signing_url"))
        emit(runtime.json_mode, session, render_signing)

    _run(ctx, work)


@case_app.command("decision")
def case_decision(ctx: typer.Context, case_id: str = typer.Argument(...)) -> None:
    """Read the published award. A 404 means it is not published yet."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            award = client.get_decision(case_id)
        emit(runtime.json_mode, award, render_decision)

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
            for poll in range(max_polls):
                case = client.get_case(case_id)
                last = case
                if not runtime.json_mode:
                    typer.echo(
                        f"{case.get('status')} turn={case.get('current_turn')} "
                        f"round={case.get('next_round')} next={case.get('next_action')}"
                    )
                if until and case.get("status") == until:
                    break
                if until_action and case.get("action_required"):
                    break
                if not until and not until_action and case.get("status") == "decided":
                    break
                if poll + 1 < max_polls:
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
    idempotency_key: Optional[str] = typer.Option(None, "--idempotency-key", help="Reuse this token to replay the same submit."),
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
        file_fields = _response_file_fields(
            via_tickets=via_tickets,
            evidence=evidence,
            evidence_response_files=evidence_response_file,
            counterclaim_files=counterclaim_file,
        )
        with runtime.client() as client:
            case = client.get_case(case_id)
            _ensure_accepted(case, list(fields) + file_fields)
            payload = client.create_response(
                case_id,
                fields,
                evidence=evidence,
                evidence_response_files=evidence_response_file,
                counterclaim_files=counterclaim_file,
                via_tickets=via_tickets,
                idempotency_key=idempotency_key,
            )
        emit(runtime.json_mode, payload, render_response_created)

    _run(ctx, work)


# --- uploads ---


@upload_app.command("sessions")
def upload_sessions(
    ctx: typer.Context,
    files: list[Path] = typer.Argument(..., help="Local files to describe."),
    role: Optional[str] = typer.Option(None, "--role", help="Ignored by the API. Kept so older commands do not fail."),
) -> None:
    """Create resumable upload sessions, PUT each file, and print tickets."""

    def work(runtime: Runtime) -> None:
        descriptors = []
        for path in files:
            if not path.is_file():
                raise FileNotFoundError(path)
            if path.stat().st_size <= 0:
                raise ConfigError(f"{path} is empty; the upload API requires size > 0.")
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
            typer.echo("Uploaded. The ticket is in the output above. Cancel an unused ticket with `dl upload cancel`.")
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
    """Create the sample claimant filing, then print the website steps that follow."""

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
                consent_fields = _pick(
                    {
                        "question_for_arbitration": fields.get("question_for_arbitration"),
                        "financial_demand_usd": fields.get("financial_demand_usd", "0.00"),
                        "other_relief": fields.get("other_relief", ""),
                        "respondent_type": fields.get("respondent_type") or "individual",
                        "respondent_first_name": fields.get("respondent_first_name"),
                        "respondent_last_name": fields.get("respondent_last_name", ""),
                        "respondent_email": fields.get("respondent_email"),
                    },
                    CONSENT_FIELDS,
                )
                _require_fields(consent_fields, _consent_required(consent_fields))
                payload = client.create_consent_case(
                    consent_fields,
                    contract_files=[contract] if contract.is_file() else [],
                )
                emit(runtime.json_mode, payload, render_consent_created)
                created = payload.get("case") or {}
                if created.get("next_action") == "sign_terms" and created.get("id"):
                    session = client.sign_consent_case(created["id"])
                    if not runtime.json_mode:
                        render_signing(session)
                if not runtime.json_mode:
                    typer.echo("\nNext: open the signing URL, then pay on the dashboard if action_url asks for it.")
                    typer.echo("A test key can finish the respondent side with `dl consent complete-respondent`.")
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
            case = payload.get("case") or {}
            if case.get("next_action") == "sign_terms" and case.get("id"):
                session = client.sign_case(case["id"])
                if not runtime.json_mode:
                    render_signing(session)
            if not runtime.json_mode:
                typer.echo("\nAfter signing, payment and identity verification are still website steps unless a test key skips them.")
                typer.echo("The respondent then claims with the emailed code, signs, and files round 1.")
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
    verification_code: Optional[str] = typer.Option(None, "--code", help="Claim with this verification code when the case is not_claimed."),
    wait_for_web: bool = typer.Option(True, "--wait-for-web/--no-wait-for-web"),
) -> None:
    """Load a case as respondent, claim and sign if needed, then submit this turn."""

    def work(runtime: Runtime) -> None:
        extra = _load_json_object(from_json)
        resolved_argument = argument or extra.get("argument")
        if not resolved_argument:
            raise ConfigError("Provide --argument or --from-json with an 'argument' field.")
        with runtime.client() as client:
            try:
                case = client.get_case(case_id)
            except APIError as exc:
                if exc.reason == "not_claimed" and verification_code:
                    case = client.claim_case(case_id, verification_code.strip())
                else:
                    raise
            if case.get("role") != "respondent" and not runtime.json_mode:
                typer.echo(
                    f"Warning: this key's role on the case is {case.get('role')!r}, not respondent. "
                    "Use --profile respondent with the respondent's API key.",
                    err=True,
                )
            emit(runtime.json_mode, case, render_case)
            if case.get("next_action") == "sign_terms":
                session = client.sign_case(case_id)
                if not runtime.json_mode:
                    render_signing(session)
            while wait_for_web and case.get("next_action") in {"sign_terms", "pay_filing_fee", "verify_identity", "complete_form"}:
                if runtime.json_mode:
                    break
                typer.echo()
                if case.get("next_action") == "sign_terms":
                    typer.echo("Open the signing URL above, then press Enter.")
                else:
                    typer.echo(f"Complete {case.get('next_action')} at:\n{case.get('action_url') or case.get('view_url')}")
                typer.prompt("Press Enter after finishing that web step", default="", show_default=False)
                case = client.get_case(case_id)
                emit(False, case, render_case)
                if case.get("next_action") == "sign_terms":
                    session = client.sign_case(case_id)
                    render_signing(session)
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
            _ensure_accepted(case, list(fields) + _response_file_fields(via_tickets=False, evidence=evidence, evidence_response_files=evidence_response_file, counterclaim_files=[]))
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


@simulation_app.command("create")
def simulation_create(
    ctx: typer.Context,
    question: Optional[str] = typer.Option(None, "--question"),
    plaintiff_name: Optional[str] = typer.Option(None, "--plaintiff-name"),
    respondent_name: Optional[str] = typer.Option(None, "--respondent-name"),
    plaintiff_argument: Optional[str] = typer.Option(None, "--plaintiff-argument"),
    respondent_argument: Optional[str] = typer.Option(None, "--respondent-argument"),
    plaintiff_rebuttal: Optional[str] = typer.Option(None, "--plaintiff-rebuttal"),
    respondent_rebuttal: Optional[str] = typer.Option(None, "--respondent-rebuttal"),
    financial_demand_usd: str = typer.Option("0.00", "--demand"),
    other_relief: str = typer.Option("", "--other-relief"),
    respondent_email: str = typer.Option("", "--respondent-email"),
    governing_contract: str = typer.Option("", "--governing-contract"),
    contract: Optional[Path] = typer.Option(None, "--contract"),
    plaintiff_documents: list[Path] = typer.Option([], "--plaintiff-document"),
    respondent_documents: list[Path] = typer.Option([], "--respondent-document"),
    plaintiff_rebuttal_documents: list[Path] = typer.Option([], "--plaintiff-rebuttal-document"),
    respondent_rebuttal_documents: list[Path] = typer.Option([], "--respondent-rebuttal-document"),
    from_json: Optional[Path] = typer.Option(None, "--from-json", "--from"),
    via_tickets: bool = typer.Option(False, "--via-tickets"),
    idempotency_key: Optional[str] = typer.Option(None, "--idempotency-key"),
) -> None:
    """Queue a simulation with a production API key. Test keys receive 403."""

    def work(runtime: Runtime) -> None:
        fields = {
            "question_for_arbitration": question,
            "plaintiff_name": plaintiff_name,
            "respondent_name": respondent_name,
            "plaintiff_argument": plaintiff_argument,
            "respondent_argument": respondent_argument,
            "plaintiff_rebuttal": plaintiff_rebuttal,
            "respondent_rebuttal": respondent_rebuttal,
            "financial_demand_usd": financial_demand_usd,
            "other_relief": other_relief,
            "respondent_email": respondent_email,
            "governing_contract": governing_contract,
        }
        fields.update(_load_json_object(from_json))
        fields = _pick(fields, SIMULATION_FIELDS)
        _require_fields(
            fields,
            [
                "question_for_arbitration",
                "plaintiff_name",
                "respondent_name",
                "plaintiff_argument",
                "respondent_argument",
            ],
        )
        with runtime.client() as client:
            payload = client.create_simulation(
                fields,
                contract_file=contract,
                plaintiff_documents=plaintiff_documents,
                respondent_documents=respondent_documents,
                plaintiff_rebuttal_documents=plaintiff_rebuttal_documents,
                respondent_rebuttal_documents=respondent_rebuttal_documents,
                via_tickets=via_tickets,
                idempotency_key=idempotency_key,
            )
        if not runtime.json_mode:
            typer.echo("Queued. Run `dl simulation list` to find this id later.")
        emit(runtime.json_mode, payload, render_simulation)

    _run(ctx, work)


@simulation_app.command("list")
def simulation_list(
    ctx: typer.Context,
    limit: int = typer.Option(50, "--limit", min=1, max=200),
    cursor: Optional[str] = typer.Option(None, "--cursor"),
) -> None:
    """List simulations owned by this production key. Test keys receive 403."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            page = client.list_simulations(limit=limit, cursor=cursor)
        _emit_page(runtime, page, "simulations", render_simulation_list)

    _run(ctx, work)


@simulation_app.command("get")
def simulation_get(ctx: typer.Context, simulation_id: str = typer.Argument(...)) -> None:
    """Poll one simulation owned by this production key."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            simulation = client.get_simulation(simulation_id)
        emit(runtime.json_mode, simulation, render_simulation)

    _run(ctx, work)


@simulation_app.command("result")
def simulation_result(ctx: typer.Context, simulation_id: str = typer.Argument(...)) -> None:
    """Read the award once status is ready."""

    def work(runtime: Runtime) -> None:
        with runtime.client() as client:
            award = client.get_simulation_result(simulation_id)
        emit(runtime.json_mode, award, render_decision)

    _run(ctx, work)


@simulation_app.command("watch")
def simulation_watch(
    ctx: typer.Context,
    simulation_id: str = typer.Argument(...),
    interval: float = typer.Option(10.0, "--interval", help="Seconds between polls."),
    max_polls: int = typer.Option(60, "--max-polls"),
) -> None:
    """Poll until the simulation is ready or failed, then print the award."""

    def work(runtime: Runtime) -> None:
        last: dict[str, Any] | None = None
        with runtime.client() as client:
            for poll in range(max_polls):
                simulation = client.get_simulation(simulation_id)
                last = simulation
                status = simulation.get("status")
                if not runtime.json_mode:
                    typer.echo(f"{status}")
                if status in {"ready", "failed"}:
                    break
                if poll + 1 < max_polls:
                    time.sleep(interval)
            else:
                if not runtime.json_mode:
                    typer.echo("Still running. Re-run `dl simulation watch` with the same id.")
            if last and last.get("status") == "ready":
                award = client.get_simulation_result(simulation_id)
                emit(runtime.json_mode, award, render_decision)
                return
        if last is not None:
            emit(runtime.json_mode, last, render_simulation)

    _run(ctx, work)


def _require_fields(fields: dict[str, Any], names: list[str]) -> None:
    missing = [name for name in names if not fields.get(name)]
    if missing:
        raise ConfigError("Missing required fields: " + ", ".join(missing))


def _consent_required(fields: dict[str, Any]) -> list[str]:
    required = ["question_for_arbitration", "respondent_first_name", "respondent_email"]
    if str(fields.get("respondent_type") or "individual").lower() != "organization":
        required.append("respondent_last_name")
    return required


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

SIMULATION_FIELDS = {
    "question_for_arbitration",
    "plaintiff_name",
    "respondent_name",
    "plaintiff_argument",
    "respondent_argument",
    "plaintiff_rebuttal",
    "respondent_rebuttal",
    "financial_demand_usd",
    "other_relief",
    "respondent_email",
    "governing_contract",
}


def _reject_cursor_offset(cursor: Optional[str], offset: int) -> None:
    if cursor and offset:
        raise ConfigError("Do not combine --cursor with a non-zero --offset.")


def _emit_page(runtime: Runtime, items: Any, key: str, render: Any) -> None:
    cursor = getattr(items, "next_cursor", None)
    payload = {key: list(items), "next_cursor": cursor}

    def draw(_payload: Any) -> None:
        render(list(items))
        render_page_cursor(cursor)

    emit(runtime.json_mode, payload, draw)


def _maybe_open(open_browser: bool, url: Any) -> None:
    if open_browser and url:
        import webbrowser

        webbrowser.open(str(url))


def _response_file_fields(
    *,
    via_tickets: bool,
    evidence: Sequence[Path],
    evidence_response_files: Sequence[Path],
    counterclaim_files: Sequence[Path],
) -> list[str]:
    names: list[str] = []
    if evidence:
        names.append("evidence_tickets" if via_tickets else "evidence")
    if evidence_response_files:
        names.append("evidence_response_files_tickets" if via_tickets else "evidence_response_files")
    if counterclaim_files:
        names.append("counterclaim_files_tickets" if via_tickets else "counterclaim_files")
    return names


def _ensure_accepted(case: dict[str, Any], names: list[str]) -> None:
    accepted = case.get("accepted_fields")
    if not isinstance(accepted, list):
        return
    if not accepted:
        raise ConfigError(
            "No response round is open. "
            f"status={case.get('status')} next_action={case.get('next_action')}."
        )
    blocked = [name for name in names if name not in accepted and name not in {"argument", "affirmation"}]
    if blocked:
        allowed = ", ".join(str(item) for item in accepted)
        raise ConfigError(
            f"Round {case.get('next_round')} does not accept: {', '.join(blocked)}. Accepted fields: {allowed}."
        )


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