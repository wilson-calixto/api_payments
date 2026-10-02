import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    logger.info(f"Receiving event: {json.dumps(event)}")
    
    
    if isinstance(event, dict) and 'body' in event:
        try:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        except json.JSONDecodeError:
            raise ValueError("Error parsing: The payload is not a valid JSON.")
    else:
        body = event

    
    required_field = "email"    

    if not body or required_field not in body:    
        raise ValueError(f"Invalid payload: The required field '{required_field}' is missing.")

    logger.info(f"Payload successfully processed for: {body[required_field]}")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Payload sucessfully processed!",
            "data": body
        })
    }