import httpx

from decisionlayer_cli.client import DecisionLayerClient


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if request.method == "GET" and path == "/api/v1/cases":
        return httpx.Response(
            200,
            json=[
                {
                    "id": "case_test",
                    "status": "awaiting_response",
                    "role": "claimant",
                    "action_required": False,
                    "current_turn": "respondent",
                    "question_for_arbitration": "Return the deposit?",
                    "financial_demand_usd": "3500.00",
                    "claimant_email": "alex@example.com",
                    "respondent_type": "individual",
                    "respondent_first_name": "Jordan",
                    "respondent_last_name": "Chen",
                    "created_at": "2026-07-03T18:20:11Z",
                    "updated_at": "2026-07-03T18:20:11Z",
                    "view_url": "https://www.decisionlayer.ai/cases/case_test/view",
                }
            ],
        )
    if request.method == "POST" and path == "/api/v1/consent-cases":
        return httpx.Response(
            201,
            json={
                "case": {"id": "consent_1", "status": "ready_to_sign", "question_for_arbitration": "Q"},
                "sign_url": "https://www.decisionlayer.ai/sign",
                "dashboard_url": "https://www.decisionlayer.ai/dashboard",
            },
        )
    if request.method == "GET" and path == "/api/v1/consent-cases":
        return httpx.Response(200, json=[])
    return httpx.Response(404, json={"error": {"status": 404, "message": path, "details": []}})


def test_list_cases_and_create_consent():
    transport = httpx.MockTransport(_handler)
    with DecisionLayerClient("dvarb_test", transport=transport) as client:
        cases = client.list_cases(action_required=True)
        assert cases[0]["id"] == "case_test"
        created = client.create_consent_case(
            {
                "question_for_arbitration": "Q",
                "respondent_first_name": "Jordan",
                "respondent_email": "jordan@example.com",
            }
        )
        assert created["case"]["id"] == "consent_1"


def test_create_case_sends_multipart(tmp_path):
    recorded = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded["content_type"] = request.headers.get("content-type", "")
        recorded["body"] = request.content
        if request.url.path == "/api/v1/cases":
            return httpx.Response(
                201,
                json={
                    "case": {"id": "case_1", "status": "awaiting_signature", "role": "claimant"},
                    "action_url": "https://www.decisionlayer.ai/terms",
                    "dashboard_url": "https://www.decisionlayer.ai/dashboard",
                    "message": "ok",
                },
            )
        return httpx.Response(404, json={})

    contract = tmp_path / "c.txt"
    contract.write_text("clause", encoding="utf-8")
    transport = httpx.MockTransport(handler)
    with DecisionLayerClient("dvarb_test", transport=transport) as client:
        result = client.create_case(
            {
                "question_for_arbitration": "Q",
                "argument": "A",
                "respondent_first_name": "Jordan",
                "respondent_email": "j@example.com",
                "claimant_affirmation": "true",
            },
            contract_file=contract,
        )
    assert result["case"]["id"] == "case_1"
    assert "multipart/form-data" in recorded["content_type"]
    assert b"question_for_arbitration" in recorded["body"]
    assert b"clause" in recorded["body"]


def test_upload_sessions_omit_role_by_default():
    recorded = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded["body"] = request.content
        return httpx.Response(
            200,
            json={
                "batch_id": "b1",
                "uploads": [
                    {
                        "upload_id": "u1",
                        "filename": "a.txt",
                        "content_type": "text/plain",
                        "size": 5,
                        "upload_url": "https://storage.example/put",
                        "ticket": "ticket_1",
                        "expires_at": "2026-09-16T18:57:56.107Z",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    with DecisionLayerClient("dvarb_test", transport=transport) as client:
        client.create_upload_sessions([{"filename": "a.txt", "size": 5, "content_type": "text/plain"}])
    assert b'"role"' not in recorded["body"]
    assert b"a.txt" in recorded["body"]


def test_upload_sessions_drop_role_when_supplied():
    recorded = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded["body"] = request.content
        return httpx.Response(200, json={"batch_id": "b", "uploads": []})

    transport = httpx.MockTransport(handler)
    with DecisionLayerClient("dvarb_test", transport=transport) as client:
        client.create_upload_sessions(
            [{"filename": "a.txt", "size": 5, "content_type": "text/plain", "role": "claimant"}]
        )
    assert b"role" not in recorded["body"]


def test_list_cases_keeps_cursor_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["cursor"] = request.url.params.get("cursor")
        seen["offset"] = request.url.params.get("offset")
        return httpx.Response(200, json=[], headers={"X-Next-Cursor": "page-2"})

    transport = httpx.MockTransport(handler)
    with DecisionLayerClient("dvarb_test", transport=transport) as client:
        page = client.list_cases(cursor="page-1", offset=5)
    assert seen["cursor"] == "page-1"
    assert seen["offset"] is None
    assert page.next_cursor == "page-2"
    assert page == []


def test_claim_is_json_and_consent_get_is_by_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["type"] = request.headers.get("content-type", "")
        seen["body"] = request.content
        if request.url.path.endswith("/claim"):
            seen["claim_body"] = request.content
            seen["claim_type"] = request.headers.get("content-type", "")
            return httpx.Response(200, json={"id": "case_1", "role": "respondent"})
        return httpx.Response(200, json={"id": "consent_9"})

    transport = httpx.MockTransport(handler)
    with DecisionLayerClient("dvarb_test", transport=transport) as client:
        claimed = client.claim_case("case_1", "abc")
        assert claimed["role"] == "respondent"
        got = client.get_consent_case("consent_9")
    assert got["id"] == "consent_9"
    assert seen["path"] == "/api/v1/consent-cases/consent_9"
    assert b"verification_code" in seen["claim_body"]
    assert "application/json" in seen["claim_type"]


def test_simulation_sends_multipart_and_idempotency_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["type"] = request.headers.get("content-type", "")
        seen["key"] = request.headers.get("Idempotency-Key")
        seen["body"] = request.content
        return httpx.Response(201, json={"id": "case_sim", "status": "processing", "page_url": "https://example/s"})

    transport = httpx.MockTransport(handler)
    with DecisionLayerClient("dvarb_test", transport=transport) as client:
        created = client.create_simulation(
            {
                "question_for_arbitration": "Q",
                "plaintiff_name": "Avery",
                "respondent_name": "Jordan",
                "plaintiff_argument": "Return it.",
                "respondent_argument": "I earned it.",
            }
        )
    assert created["id"] == "case_sim"
    assert "multipart/form-data" in seen["type"]
    assert seen["key"]
    assert b"question_for_arbitration" in seen["body"]
    assert b"contract_file" in seen["body"]


def test_create_case_idempotency_keys_differ():
    keys = []

    def handler(request: httpx.Request) -> httpx.Response:
        keys.append(request.headers.get("Idempotency-Key"))
        return httpx.Response(
            201,
            json={"case": {"id": "case_1", "status": "awaiting_signature"}, "action_url": "https://example"},
        )

    transport = httpx.MockTransport(handler)
    with DecisionLayerClient("dvarb_test", transport=transport) as client:
        client.create_consent_case({"question_for_arbitration": "Q", "respondent_first_name": "J", "respondent_email": "j@example.com"})
        client.create_consent_case(
            {"question_for_arbitration": "Q", "respondent_first_name": "J", "respondent_email": "j@example.com"},
            idempotency_key="same-key",
        )
        client.create_consent_case(
            {"question_for_arbitration": "Q", "respondent_first_name": "J", "respondent_email": "j@example.com"},
            idempotency_key="same-key",
        )
    assert keys[0] and keys[0] != "same-key"
    assert keys[1] == keys[2] == "same-key"
