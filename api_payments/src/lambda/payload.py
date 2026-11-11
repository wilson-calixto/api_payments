import json


def parse_payload(event):
    if isinstance(event, str):
        try:
            event = json.loads(event)
        except json.JSONDecodeError as exc:
            raise ValueError("Error parsing: The payload is not a valid JSON.") from exc

    if not isinstance(event, dict):
        raise ValueError("Error parsing: The payload is not a valid JSON.")

    if "Records" in event and event["Records"]:
        record = event["Records"][0]
        body = record.get("body", record)
        return parse_payload(body)

    if "body" in event:
        body = event["body"]
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError as exc:
                raise ValueError("Error parsing: The payload is not a valid JSON.") from exc
        if isinstance(body, dict):
            return body

    return event
