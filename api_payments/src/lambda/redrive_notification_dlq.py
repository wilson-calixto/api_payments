"""Replay notification DLQ records to the failure topic.

This function is intentionally invoked on demand (or by an operator runbook),
so a bad notification cannot create an automatic retry loop.
"""
import json
import os

import boto3

sqs = boto3.client("sqs")
sns = boto3.client("sns")


def handler(event, context):
    records = event.get("Records") or _receive_batch()
    replayed = 0
    for record in records:
        body = record.get("body", record)
        try:
            envelope = json.loads(body) if isinstance(body, str) else body
            message = envelope.get("Message", envelope)
            if isinstance(message, str):
                json.loads(message)
            parsed = json.loads(message) if isinstance(message, str) else message
            topic_by_event = {
                "PAYMENT_APPROVED": os.environ["PAYMENT_SUCCESS_TOPIC_ARN"],
                "PAYMENT_REJECTED": os.environ["PAYMENT_ERROR_TOPIC_ARN"],
                "PAYMENT_FAILED": os.environ["PAYMENT_FAILURE_TOPIC_ARN"],
            }
            topic_arn = topic_by_event.get(parsed.get("eventType"), os.environ["PAYMENT_FAILURE_TOPIC_ARN"])
            sns.publish(
                TopicArn=topic_arn,
                Message=message if isinstance(message, str) else json.dumps(message),
                Subject="Payment notification redrive",
            )
            if record.get("receiptHandle"):
                sqs.delete_message(
                    QueueUrl=os.environ["NOTIFICATION_DLQ_URL"],
                    ReceiptHandle=record["receiptHandle"],
                )
            replayed += 1
        except Exception:
            # Leave malformed records in the DLQ for inspection.
            raise
    return {"replayed": replayed}


def _receive_batch():
    return sqs.receive_message(
        QueueUrl=os.environ["NOTIFICATION_DLQ_URL"],
        MaxNumberOfMessages=10,
        WaitTimeSeconds=1,
        VisibilityTimeout=60,
    ).get("Messages", [])
