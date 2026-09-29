"""Archwares™ vendored DecisionLayer example: create a consent arbitration case.

The guide at /api/create-a-consent-case hardcodes API_KEY and
BASE_URL = https://www.decisionlayer.ai. This copy reads
DECISIONLAYER_API_KEY and DECISIONLAYER_BASE_URL instead.
Default base URL is staging.

Then run:

    pip install requests
    python create_consent_case.py
"""

import os
import uuid

import requests

API_KEY = os.environ.get("DECISIONLAYER_API_KEY", "PASTE_YOUR_KEY_HERE")
BASE_URL = os.environ.get("DECISIONLAYER_BASE_URL", "https://staging.decisionlayer.ai").rstrip("/")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def main() -> None:
    with open("sample_contract.txt", "w", encoding="utf-8") as handle:
        handle.write("Sample contract for the DecisionLayer consent demo.\n")

    data = {
        "question_for_arbitration": "Respondent kept a $3,500 deposit.",
        "financial_demand_usd": "3500.00",
        "other_relief": "Return of any project files.",
        "respondent_first_name": "Jordan",
        "respondent_last_name": "Chen",
        "respondent_email": "jordan.chen@example.com",
    }

    with open("sample_contract.txt", "rb") as contract:
        files = {
            "contract_files": ("sample_contract.txt", contract, "text/plain"),
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/consent-cases",
            headers={**HEADERS, "Idempotency-Key": str(uuid.uuid4())},
            data=data,
            files=files,
            timeout=60,
        )

    if response.status_code != 201:
        print(f"Request failed ({response.status_code}):")
        print(response.json())
        raise SystemExit(1)

    result = response.json()
    case = result["case"]
    print(f"Created consent case: {case['id']}")
    print(f"Status: {case['status']}")
    print(f"Sign it here: {result['sign_url']}")

    listing = requests.get(f"{BASE_URL}/api/v1/consent-cases", headers=HEADERS, timeout=60)
    listing.raise_for_status()
    print(f"You now have {len(listing.json())} consent case(s) on this page.")
    cursor = listing.headers.get("X-Next-Cursor")
    if cursor:
        print(f"Next cursor: {cursor}")


if __name__ == "__main__":
    main()
