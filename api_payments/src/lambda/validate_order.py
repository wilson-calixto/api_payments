import json
import logging
import uuid

from payload import parse_payload

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    logger.info("Receiving event: %s", json.dumps(event))

    body = parse_payload(event)
    required_fields = ("valor", "userId")

    if not body:
        raise ValueError("Invalid payload: a JSON object is required.")
    missing_fields = [
        field
        for field in required_fields
        if field not in body or body[field] is None or body[field] == ""
    ]
    if missing_fields:
        raise ValueError(
            "Invalid payload: missing required field(s): " + ", ".join(missing_fields)
        )

    valor = body.get("valor", 0)
    try:
        valor = float(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid payload: The field 'valor' must be numeric.") from exc

    logger.info("Validating order value: %s", valor)

    if valor <= 0:
        return {
            "status": "REJECTED",
            "valor": valor,
            "payment_id": str(uuid.uuid4()),
            "motivo": "Invalid order value",
        }

    return {
        "status": "APPROVED",
        "valor": valor,
        "payment_id": str(uuid.uuid4()),
    }
