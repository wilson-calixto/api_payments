import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api_payments" / "src" / "lambda"))

from payload import parse_payload  # noqa: E402
from validate_order import handler as validate_handler  # noqa: E402


def test_parse_sqs_body_string():
    payload = parse_payload({"body": '{"valor": 100}'})
    assert payload["valor"] == 100


def test_validate_approved():
    result = validate_handler({"valor": 100, "userId": "user-001"}, None)
    assert result["status"] == "APPROVED"
    assert result["payment_id"]


def test_validate_rejected_zero():
    result = validate_handler({"valor": 0, "userId": "user-001"}, None)
    assert result["status"] == "REJECTED"
    assert result["payment_id"]


def test_validate_missing_field_raises():
    try:
        validate_handler({"valor": 100}, None)
    except ValueError as exc:
        assert "userId" in str(exc)
    else:
        raise AssertionError("expected ValueError")
