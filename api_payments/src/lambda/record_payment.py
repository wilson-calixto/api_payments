"""Persist the approved payment and its domain event atomically.

The event id is deterministic so Step Functions retries cannot create a second
payment or a second audit record.
"""
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from payload import parse_payload

dynamodb = boto3.resource("dynamodb")


def handler(event, context):
    state = parse_payload(event)
    validation = state["resultado_validacao"]
    payment = state["resultado_pagamento"]
    payment_id = validation["payment_id"]
    transaction_id = payment["transaction_id"]
    event_id = f"PAYMENT_APPROVED#{payment_id}"
    now = datetime.now(timezone.utc).isoformat()
    amount = Decimal(str(validation["valor"]))

    try:
        dynamodb.meta.client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": os.environ["TRANSACTIONS_TABLE_NAME"],
                        "Key": {"paymentId": {"S": payment_id}},
                        "UpdateExpression": (
                            "SET #status=:status, transactionId=:transactionId, "
                            "amount=:amount, userId=:userId, updatedAt=:updatedAt"
                        ),
                        "ExpressionAttributeNames": {"#status": "status"},
                        "ExpressionAttributeValues": {
                            ":status": {"S": "APPROVED"},
                            ":transactionId": {"S": transaction_id},
                            ":amount": {"N": str(amount)},
                            ":userId": {"S": state["userId"]},
                            ":updatedAt": {"S": now},
                        },
                    }
                },
                {
                    "Put": {
                        "TableName": os.environ["PAYMENT_EVENTS_TABLE_NAME"],
                        "Item": {
                            "eventId": {"S": event_id},
                            "eventType": {"S": "PAYMENT_APPROVED"},
                            "paymentId": {"S": payment_id},
                            "transactionId": {"S": transaction_id},
                            "occurredAt": {"S": now},
                        },
                        "ConditionExpression": "attribute_not_exists(eventId)",
                    }
                },
            ]
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        # A retry after a successful transaction is safe and should proceed to
        # SNS publication rather than fail the whole payment execution.
        existing = dynamodb.Table(os.environ["PAYMENT_EVENTS_TABLE_NAME"]).get_item(
            Key={"eventId": event_id}, ConsistentRead=True
        ).get("Item")
        if not existing:
            raise

    return {
        "status": "APPROVED",
        "payment_id": payment_id,
        "transaction_id": transaction_id,
        "event_id": event_id,
    }
