import json
import os
import boto3

sqs = boto3.client('sqs')
QUEUE_URL = os.environ['QUEUE_URL']

def handler(event, context):
    print("Received API request:", json.dumps(event))
    
    body = event.get('body') or '{}'
    try:
        payload = json.loads(body)
    except Exception:
        payload = {"info": "Request processed successfully"}
        
    authorizer_claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
    user_email = authorizer_claims.get('email', 'unknown-user@example.com')
    
    message_body = {
        "user_email": user_email,
        "payload": payload
    }
    
    response = sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(message_body)
    )
    
    return {
        'statusCode': 202,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'message': 'Request received and queued for processing asynchronously!',
            'messageId': response['MessageId']
        })
    }
