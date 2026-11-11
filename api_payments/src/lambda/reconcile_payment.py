"""Mark an approved payment as queued for financial reconciliation.

The SNS message id is not used as identity: the payment id is the domain key,
which makes SNS redelivery harmless.
"""
import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TRANSACTIONS_TABLE_NAME"])
events_table = dynamodb.Table(os.environ["PAYMENT_EVENTS_TABLE_NAME"])


def handler(event, context):
    for record in event.get("Records", []):
        message = json.loads(record["Sns"]["Message"])
        now = datetime.now(timezone.utc).isoformat()
        table.update_item(
            Key={"paymentId": message["paymentId"]},
            UpdateExpression=(
                "SET reconciliationStatus=:status, reconciliationStartedAt=:startedAt"
            ),
            ExpressionAttributeValues={":status": "STARTED", ":startedAt": now},
        )
        try:
            events_table.put_item(
                Item={
                    "eventId": f"RECONCILIATION_STARTED#{message['paymentId']}",
                    "eventType": "RECONCILIATION_STARTED",
                    "paymentId": message["paymentId"],
                    "occurredAt": now,
                },
                ConditionExpression="attribute_not_exists(eventId)",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
        logger.info("Reconciliation started for payment %s", message["paymentId"])
    return {"status": "STARTED"}
