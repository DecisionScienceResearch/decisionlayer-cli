from decisionlayer_cli.errors import parse_error_body, raise_for_status, APIError
import httpx


def test_parse_documented_envelope():
    message, details = parse_error_body(
        {
            "error": {
                "status": 422,
                "message": "Your request could not be processed.",
                "details": ["Field 'respondent_email' is required."],
            }
        }
    )
    assert message.startswith("Your request")
    assert details == ["Field 'respondent_email' is required."]


def test_parse_fastapi_validation():
    message, details = parse_error_body(
        {
            "detail": [
                {
                    "loc": ["body", "argument"],
                    "msg": "Field required",
                    "type": "missing",
                }
            ]
        }
    )
    assert message == "Validation failed."
    assert "argument: Field required" in details[0]


def test_raise_for_status_401():
    response = httpx.Response(
        401,
        json={"error": {"status": 401, "message": "Invalid or missing API key", "details": []}},
        request=httpx.Request("GET", "https://www.decisionlayer.ai/api/v1/cases"),
    )
    try:
        raise_for_status(response)
    except APIError as exc:
        assert exc.status_code == 401
        assert "dvarb_" in exc.hint
        assert exc.reason == ""
    else:
        raise AssertionError("expected APIError")


def test_reason_not_claimed():
    response = httpx.Response(
        404,
        json={"error": {"status": 404, "message": "Not claimed", "details": ["Claim first."], "reason": "not_claimed"}},
        request=httpx.Request("GET", "https://staging.decisionlayer.ai/api/v1/cases/case_1"),
    )
    try:
        raise_for_status(response)
    except APIError as exc:
        assert exc.reason == "not_claimed"
        assert "claim" in exc.hint
    else:
        raise AssertionError("expected APIError")


def test_unpublished_decision_404_keeps_server_details():
    response = httpx.Response(
        404,
        json={
            "error": {
                "status": 404,
                "message": "No published decision is available for this case.",
                "details": ["Case case_1 has no award you can read yet."],
            }
        },
        request=httpx.Request("GET", "https://staging.decisionlayer.ai/api/v1/cases/case_1/decision"),
    )
    try:
        raise_for_status(response)
    except APIError as exc:
        assert exc.reason == ""
        assert exc.hint == ""
        assert "no award" in exc.details[0]
    else:
        raise AssertionError("expected APIError")
