import json
import logging
import os
import time

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
ses = boto3.client("sesv2")


def handler(event, context):
    """Send one payment email per SNS publication, even when SNS retries delivery."""
    for record in event.get("Records", []):
        notification = record["Sns"]
        message = _parse_message(notification["Message"])
        notification_id = notification["MessageId"]

        if not _claim_notification(notification_id, message):
            logger.info("Ignoring duplicate SNS notification %s", notification_id)
            continue

        try:
            user = _get_user(message["userId"])
            _send_email(user, message)
        except Exception:
            _release_notification(notification_id)
            raise

        _notifications_table().update_item(
            Key={"notificationId": notification_id},
            UpdateExpression="SET #status = :sent",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":sent": "SENT"},
        )
        logger.info(
            "Payment notification sent: eventType=%s userId=%s paymentId=%s",
            message["eventType"],
            message["userId"],
            message["paymentId"],
        )


def _parse_message(raw_message):
    try:
        message = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise ValueError("SNS message must be a JSON object.") from exc

    if not isinstance(message, dict):
        raise ValueError("SNS message must be a JSON object.")
    required_fields = ("eventType", "userId", "paymentId", "amount")
    missing_fields = [field for field in required_fields if field not in message]
    if missing_fields:
        raise ValueError("SNS message is missing: " + ", ".join(missing_fields))
    if message["eventType"] not in {"PAYMENT_APPROVED", "PAYMENT_REJECTED", "PAYMENT_FAILED"}:
        raise ValueError("Unsupported payment event type.")
    return message


def _claim_notification(notification_id, message):
    try:
        _notifications_table().put_item(
            Item={
                "notificationId": notification_id,
                "paymentId": message["paymentId"],
                "eventType": message["eventType"],
                "status": "PROCESSING",
                "expiresAt": int(time.time()) + 60 * 60 * 24 * 90,
            },
            ConditionExpression="attribute_not_exists(notificationId)",
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def _release_notification(notification_id):
    _notifications_table().delete_item(Key={"notificationId": notification_id})


def _get_user(user_id):
    response = _users_table().get_item(Key={"userId": user_id}, ConsistentRead=True)
    user = response.get("Item")
    if not user:
        raise ValueError(f"User not found for userId={user_id}")
    if not user.get("email") or not user.get("emailVerified"):
        raise ValueError(f"User does not have a verified email for userId={user_id}")
    return user


def _users_table():
    return dynamodb.Table(os.environ["USERS_TABLE_NAME"])


def _notifications_table():
    return dynamodb.Table(os.environ["NOTIFICATIONS_TABLE_NAME"])


def _send_email(user, message):
    approved = message["eventType"] == "PAYMENT_APPROVED"
    if approved:
        subject = "Payment approved"
        text = (
            f"Hi, {user['name']}.\n\n"
            f"Your payment of R$ {message['amount']:.2f} was approved.\n"
            f"Payment identifier: {message['paymentId']}\n"
            f"Transaction identifier: {message['transactionId']}\n"
        )
    else:
        subject = "Payment not approved"
        text = (
            f"Hi, {user['name']}.\n\n"
            f"It was not possible to approve your payment of R$ {message['amount']:.2f}.\n"
            f"Reason: {message.get('reason', 'Not informed')}\n"
            f"Payment identifier: {message['paymentId']}\n"
        )

    ses.send_email(
        FromEmailAddress=os.environ["SENDER_EMAIL"],
        Destination={"ToAddresses": [user["email"]]},
        Content={
            "Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": text, "Charset": "UTF-8"}},
            }
        },
    )
