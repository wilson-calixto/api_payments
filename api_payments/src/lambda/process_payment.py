import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    logger.info(f"Processing payment: {json.dumps(event)}")
    
    # If the payload indicates a bank API failure, we raise an unhandled exception
    if event.get("simulate_bank_error"):
        raise Exception("BankConnectionError: Failed to communicate with the payment gateway.")
        
    return {"status": "PAID", "transaction_id": "TX998877"}