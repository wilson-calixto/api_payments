import os
import json
import boto3

sfn = boto3.client('stepfunctions')

def handler(event, context):
    if isinstance(event, dict) and 'body' in event:
        try:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        except json.JSONDecodeError:
            raise ValueError("Error parsing: The payload is not a valid JSON.")
    else:
        body = event

    sfn.start_execution(
        stateMachineArn=os.environ['STATE_MACHINE_ARN'],
        input=json.dumps(body)
    )