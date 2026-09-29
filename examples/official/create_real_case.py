"""DecisionLayer API: file an arbitration case by contract and track it.

The guide at /api/create-a-case hardcodes API_KEY, BASE_URL
(https://www.decisionlayer.ai), CASE_ID, and VERIFICATION_CODE.
This copy reads those from the environment. Default base URL is staging.

Respondents set CASE_ID to the notified case id and, to claim in this
run, VERIFICATION_CODE. Leave both blank to file a new case.

    pip install requests
    python create_real_case.py
"""

from __future__ import annotations

import mimetypes
import os
import time
import uuid

import requests

API_KEY = os.environ.get("DECISIONLAYER_API_KEY", "PASTE_YOUR_KEY_HERE")
BASE_URL = os.environ.get("DECISIONLAYER_BASE_URL", "https://staging.decisionlayer.ai").rstrip("/")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
CASE_ID = os.environ.get("CASE_ID", "")
VERIFICATION_CODE = os.environ.get("VERIFICATION_CODE", "")
LARGE_FILE_BYTES = 8 * 1024 * 1024
TICKET_FIELDS = {
    "contract_file": "contract_file_ticket",
    "evidence": "evidence_tickets",
    "evidence_response_files": "evidence_response_files_tickets",
    "counterclaim_files": "counterclaim_files_tickets",
}
_signing_started: set[str] = set()


def write_sample_file(name: str, text: str) -> str:
    with open(name, "w", encoding="utf-8") as handle:
        handle.write(text)
    return name


def idempotent_headers() -> dict:
    headers = dict(HEADERS)
    headers["Idempotency-Key"] = str(uuid.uuid4())
    return headers


def upload_large_file(path: str) -> str:
    with open(path, "rb") as handle:
        body = handle.read()
    prepared = requests.post(
        f"{BASE_URL}/api/v1/uploads",
        headers=HEADERS,
        json={"files": [{"filename": os.path.basename(path), "size": len(body)}]},
        timeout=60,
    )
    prepared.raise_for_status()
    upload = prepared.json()["uploads"][0]
    put = requests.put(
        upload["upload_url"],
        headers={
            "Content-Type": upload["content_type"],
            "Content-Length": str(len(body)),
        },
        data=body,
        timeout=300,
    )
    put.raise_for_status()
    return upload["ticket"]


def append_attachment(parts: list, handles: list, field: str, path: str) -> None:
    if os.path.getsize(path) >= LARGE_FILE_BYTES:
        parts.append((TICKET_FIELDS[field], (None, upload_large_file(path))))
        return
    handle = open(path, "rb")
    handles.append(handle)
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    parts.append((field, (os.path.basename(path), handle, mime)))


def post_form(url: str, fields: dict, attachments: list) -> requests.Response:
    parts = [(name, (None, value)) for name, value in fields.items()]
    handles: list = []
    try:
        for field, path in attachments:
            append_attachment(parts, handles, field, path)
        return requests.post(url, headers=idempotent_headers(), files=parts, timeout=60)
    finally:
        for handle in handles:
            handle.close()


def create_case() -> dict:
    write_sample_file("sample_contract.txt", "Sample contract for the DecisionLayer demo.\n")
    write_sample_file("sample_evidence.txt", "Sample evidence: deposit receipt.\n")
    data = {
        "question_for_arbitration": "Respondent kept a $3,500 deposit.",
        "argument": (
            "The contract required return of the deposit within 30 days. "
            "It has been 90 days and the deposit has not been returned."
        ),
        "financial_demand_usd": "3500.00",
        "respondent_first_name": "Jordan",
        "respondent_last_name": "Chen",
        "respondent_email": "jordan.chen@example.com",
        "respondent_street_address": "12 Main St",
        "respondent_city": "Austin",
        "respondent_state": "TX",
        "respondent_zipcode": "78701",
        "claimant_street_address": "800 Oak Ave",
        "claimant_city": "Denver",
        "claimant_state": "CO",
        "claimant_zipcode": "80202",
        "claimant_affirmation": "true",
    }
    response = post_form(
        f"{BASE_URL}/api/v1/cases",
        data,
        [("contract_file", "sample_contract.txt"), ("evidence", "sample_evidence.txt")],
    )
    if response.status_code != 201:
        print(f"Create failed ({response.status_code}):")
        print(response.json())
        raise SystemExit(1)
    result = response.json()
    case = result["case"]
    print(f"Created case: {case['id']} (status: {case['status']})")
    print(f"Next step: {case['next_action']}")
    print(f"Finish it here: {result['action_url']}")
    print("Payment and identity verification follow there after you sign.")
    return case


def who_am_i() -> dict:
    response = requests.get(f"{BASE_URL}/api/v1/me", headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.json()


def claim_case(case_id: str, code: str) -> dict:
    response = requests.post(
        f"{BASE_URL}/api/v1/cases/{case_id}/claim",
        headers=HEADERS,
        json={"verification_code": code},
        timeout=60,
    )
    if response.status_code != 200:
        print(f"Claim failed ({response.status_code}):")
        print(response.json())
        raise SystemExit(1)
    case = response.json()
    print(f"Claimed case: {case_id} (role: {case['role']})")
    return case


def get_case(case_id: str) -> dict:
    response = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}", headers=HEADERS, timeout=60)
    if response.status_code == 404:
        error = response.json()["error"]
        if error.get("reason") == "not_claimed":
            code = VERIFICATION_CODE.strip()
            if code:
                print("This case has not been claimed yet. Claiming it now.")
                return claim_case(case_id, code)
            print("This case has not been claimed yet.")
            for detail in error["details"]:
                print(f"  - {detail}")
            raise SystemExit(1)
    response.raise_for_status()
    return response.json()


def list_cases_needing_action() -> list:
    response = requests.get(
        f"{BASE_URL}/api/v1/cases",
        headers=HEADERS,
        params={"action_required": "true"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def list_events() -> dict:
    response = requests.get(f"{BASE_URL}/api/v1/events", headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.json()


def list_responses(case_id: str) -> list:
    response = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}/responses", headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.json()


def print_thread(case_id: str) -> None:
    thread = list_responses(case_id)
    print(f"{len(thread)} response(s) on the case:")
    for entry in thread:
        names = ", ".join(item["name"] for item in entry["evidence_files"]) or "no files"
        argument = entry["argument"] or "no argument"
        print(
            f"  Round {entry['round']} by the {entry['submitted_by']} "
            f"at {entry['submitted_at']}: {argument[:60]} [{names}]"
        )


def submit_response(case_id: str, argument: str, evidence_paths=()) -> dict | None:
    case = get_case(case_id)
    accepted = case.get("accepted_fields") or []
    print(f"Next round: {case.get('next_round')}")
    print(f"Accepted fields: {', '.join(accepted) or 'none'}")
    data = {"argument": argument, "affirmation": "true"}
    if "evidence_demands" in accepted:
        data["evidence_demands"] = "The claimant's March bank statement."
    attachments = [("evidence", path) for path in evidence_paths] if "evidence" in accepted else []
    response = post_form(f"{BASE_URL}/api/v1/cases/{case_id}/responses", data, attachments)
    if response.status_code == 409:
        print("Not your turn yet:")
        for detail in response.json()["error"]["details"]:
            print(f"  - {detail}")
        return None
    if response.status_code == 422:
        print("The response was rejected:")
        for detail in response.json()["error"]["details"]:
            print(f"  - {detail}")
        return None
    response.raise_for_status()
    result = response.json()
    submitted = result["response"]
    print(f"Response submitted. Round {submitted['round']} is on record.")
    case = result["case"]
    if case["action_required"]:
        print(f"Waiting on you: {case['next_action']} -> {case['action_url']}")
    return result


def start_signing(case_id: str) -> dict | None:
    response = requests.post(f"{BASE_URL}/api/v1/cases/{case_id}/sign", headers=HEADERS, timeout=60)
    if response.status_code == 409:
        print("Signing is not available yet:")
        for detail in response.json()["error"]["details"]:
            print(f"  - {detail}")
        return None
    response.raise_for_status()
    session = response.json()
    print(f"Sign the terms: {session['signing_url']}")
    print(f"Provider: {session['provider']}; open it before {session['expires_at']}.")
    return session


def follow_next_action(case: dict) -> None:
    if not case.get("action_required"):
        return
    if case.get("next_action") == "sign_terms":
        case_id = case["id"]
        if case_id in _signing_started:
            print("Still waiting on you to sign. Open the signing URL above.")
            return
        if start_signing(case_id):
            _signing_started.add(case_id)
        return
    print(f"Waiting on you: {case['next_action']} -> {case['action_url']}")


def show_decision(case: dict) -> None:
    response = requests.get(f"{BASE_URL}/api/v1/cases/{case['id']}/decision", headers=HEADERS, timeout=60)
    if response.status_code == 404:
        print(f"The award is not published yet. View the case online: {case['view_url']}")
        return
    response.raise_for_status()
    award = response.json()
    print(f"The decision is ready. View it online: {case['view_url']}")
    print(award["text"])
    if award.get("pdf_url"):
        print(f"PDF: {award['pdf_url']}")


def main() -> None:
    me = who_am_i()
    print(f"Using API key for {me['email']}")
    case_id = CASE_ID.strip()
    if case_id:
        case = get_case(case_id)
        print(f"Using existing case: {case_id} (role: {case['role']}, status: {case['status']})")
    else:
        case = create_case()
        case_id = case["id"]

    for _ in range(5):
        case = get_case(case_id)
        status, turn = case["status"], case["current_turn"]
        print(f"Status: {status}, turn: {turn}")
        if status == "decided":
            show_decision(case)
            return
        follow_next_action(case)
        if status == "awaiting_response" and turn == case["role"]:
            reply_evidence = write_sample_file("sample_reply_evidence.txt", "Sample evidence: the signed addendum.\n")
            submitted = submit_response(
                case_id,
                "Section 4.2 does not apply; the termination was mutual.",
                evidence_paths=[reply_evidence],
            )
            if submitted:
                print_thread(case_id)
        time.sleep(5)

    pending = list_cases_needing_action()
    print(f"You have {len(pending)} case(s) waiting on you.")
    feed = list_events()
    print(f"{len(feed['events'])} event(s) on the change feed.")
    print("Still in progress. Re-run later, or check your dashboard.")
    print(f"You can always view the case online: {case['view_url']}")


if __name__ == "__main__":
    main()
