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

    
    required_field = "valor"

    if not body or required_field not in body:    
        raise ValueError(f"Invalid payload: The required field '{required_field}' is missing.")

    logger.info(f"Payload successfully processed for: {body[required_field]}")
    logger.info(f"Validating order: {json.dumps(event)}")
    
    valor = event.get("valor", 0)
    
    if valor <= 0:
        # Erro de negócio tratado pelo fluxo condicional Choice
        return {"status": "REJECTED", "motivo": "Invalid order value"}
        
    return {"status": "APPROVED", "valor": valor}