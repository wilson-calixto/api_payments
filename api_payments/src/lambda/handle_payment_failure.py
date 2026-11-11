"""Normalize, classify and persist failures from the payment state machine."""
import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from payload import parse_payload

dynamodb = boto3.resource("dynamodb")


def handler(event, context):
    state = parse_payload(event)
    validation = state.get("resultado_validacao", {})
    error = state.get("erro_processamento", {})
    rejected = validation.get("status") == "REJECTED" and not error
    if rejected:
        raw = validation.get("motivo", "Order rejected")
        details = {"message": raw}
    else:
        raw = error.get("Cause") or error.get("Error") or "Payment processing failed"
        try:
            details = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            details = {"message": raw}
    description = str(details.get("message") or details.get("Message") or raw)
    code = str(details.get("errorCode") or details.get("Error") or ("ORDER_REJECTED" if rejected else "PAYMENT_PROCESSING_ERROR"))
    category, retryable = ("NEGOCIO", False) if rejected else _classify(code, description)
    payment_id = validation.get("payment_id") or f"unknown-{context.aws_request_id}"
    now = datetime.now(timezone.utc).isoformat()
    event_type = "PAYMENT_REJECTED" if rejected else "PAYMENT_FAILED"
    event_id = f"{event_type}#{payment_id}"
    amount = Decimal(str(validation.get("valor", 0)))
    item = {
        "paymentId": payment_id,
        "status": "REJECTED" if rejected else "FAILED",
        "amount": amount,
        "userId": state.get("userId", "unknown"),
        "failureCategory": category,
        "errorCode": code,
        "errorDescription": description,
        "retryable": retryable,
        "technicalContext": {
            "rawError": raw,
            "lambdaRequestId": context.aws_request_id,
        },
        "updatedAt": now,
    }
    dynamodb.Table(os.environ["TRANSACTIONS_TABLE_NAME"]).put_item(Item=item)
    try:
        dynamodb.Table(os.environ["PAYMENT_EVENTS_TABLE_NAME"]).put_item(
            Item={
                "eventId": event_id,
                "eventType": event_type,
                "paymentId": payment_id,
                "failureCategory": category,
                "errorCode": code,
                "errorDescription": description,
                "retryable": retryable,
                "occurredAt": now,
            },
            ConditionExpression="attribute_not_exists(eventId)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
    return {
        "status": "REJECTED" if rejected else "FAILED",
        "payment_id": payment_id,
        "amount": float(amount),
        "error_code": code,
        "error_description": description,
        "failure_category": category,
        "retryable": retryable,
        "source_system": state.get("sourceSystem", "api-payments"),
        "event_id": event_id,
    }


def _classify(code, description):
    value = f"{code} {description}".lower()
    if any(word in value for word in ("fraud", "antifraud", "anti-fraud")):
        return "ANTIFRAUDE", False
    if any(word in value for word in ("insufficient", "declined", "limit", "funds")):
        return "FINANCEIRA", False
    if any(word in value for word in ("invalid", "order", "validation", "payload")):
        return "NEGOCIO", False
    return "TECNICA", any(word in value for word in ("timeout", "connection", "network", "gateway", "tempor"))
