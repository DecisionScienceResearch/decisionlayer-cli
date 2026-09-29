"""Archwares™ vendored DecisionLayer example: run a simulation in one request.

The guide at /api/run-a-simulation hardcodes a production URL and a
constant API key. This copy reads DECISIONLAYER_API_KEY and
DECISIONLAYER_BASE_URL. Simulations reject test keys with 403.

    pip install requests
    python run_simulation.py
"""

import os
import time
import uuid

import requests

API_KEY = os.environ.get("DECISIONLAYER_API_KEY", "PASTE_YOUR_KEY_HERE")
BASE_URL = os.environ.get("DECISIONLAYER_BASE_URL", "https://staging.decisionlayer.ai").rstrip("/")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def main() -> None:
    data = {
        "question_for_arbitration": "Did the respondent owe the deposit back?",
        "governing_contract": (
            "The parties agreed that any dispute over the deposit would be "
            "decided in arbitration, and that the deposit is refundable if "
            "the work was not delivered within 30 days."
        ),
        "financial_demand_usd": "3500.00",
        "plaintiff_name": "Avery Quinn",
        "respondent_name": "Jordan Chen",
        "plaintiff_argument": (
            "The contract required the deposit to be returned within 30 days "
            "if delivery slipped. Delivery slipped, and the deposit was kept."
        ),
        "respondent_argument": (
            "Delivery was late because the claimant changed the scope. The "
            "deposit was earned."
        ),
        "plaintiff_rebuttal": "The scope change was never agreed in writing.",
        "respondent_rebuttal": "The emails of March 2 accepted the new scope.",
    }

    # requests urlencodes when files= is omitted. This endpoint is multipart
    # even when every attachment is text, so pass an empty file part.
    response = requests.post(
        f"{BASE_URL}/api/v1/simulations",
        headers={**HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        data=data,
        files={"contract_file": ("", b"", "application/octet-stream")},
        timeout=60,
    )
    if response.status_code != 201:
        print(f"Request failed ({response.status_code}):")
        print(response.json())
        raise SystemExit(1)

    created = response.json()
    simulation_id = created["id"]
    print(f"Queued simulation: {simulation_id}")
    print(f"Status: {created['status']}")
    print(f"Page: {created['page_url']}")

    for _attempt in range(60):
        status = requests.get(
            f"{BASE_URL}/api/v1/simulations/{simulation_id}",
            headers=HEADERS,
            timeout=60,
        )
        status.raise_for_status()
        body = status.json()
        print(f"Status: {body['status']}")
        if body["status"] == "failed":
            print(body.get("message"))
            raise SystemExit(1)
        if body["status"] == "ready":
            result = requests.get(
                f"{BASE_URL}/api/v1/simulations/{simulation_id}/result",
                headers=HEADERS,
                timeout=60,
            )
            result.raise_for_status()
            award = result.json()
            print(f"Result URL: {award['pdf_url']}")
            print(f"Page: {award['page_url']}")
            print(award["text"])
            return
        time.sleep(10)

    print("Still running. Poll GET /api/v1/simulations/{id} and then GET .../result.")


if __name__ == "__main__":
    main()
