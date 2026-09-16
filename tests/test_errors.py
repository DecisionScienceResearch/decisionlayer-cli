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
    else:
        raise AssertionError("expected APIError")
