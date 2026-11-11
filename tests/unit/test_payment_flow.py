import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api_payments" / "src" / "lambda"))

from process_payment import handler as process_payment  # noqa: E402
from validate_order import handler as validate_order  # noqa: E402


def test_approved_payment_reaches_processing_lambda():
    input_payload = {"valor": 100, "userId": "user-001"}

    validation = validate_order(input_payload, None)
    assert validation["status"] == "APPROVED"

    payment = process_payment(
        {**input_payload, "resultado_validacao": validation}, None
    )
    assert payment["status"] == "PAID"
    assert payment["transaction_id"].startswith("TX-")


def test_rejected_payment_does_not_require_processing_lambda():
    validation = validate_order({"valor": 0, "userId": "user-001"}, None)

    assert validation["status"] == "REJECTED"
    assert validation["motivo"] == "Invalid order value"
