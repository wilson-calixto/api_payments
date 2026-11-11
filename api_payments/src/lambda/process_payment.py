import json
import logging
import uuid

from payload import parse_payload

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    logger.info("Processing payment: %s", json.dumps(event))

    body = parse_payload(event)

    if body.get("simulate_bank_error"):
        raise Exception("BankConnectionError: Failed to communicate with the payment gateway.")

    return {"status": "PAID", "transaction_id": f"TX-{uuid.uuid4()}"}
