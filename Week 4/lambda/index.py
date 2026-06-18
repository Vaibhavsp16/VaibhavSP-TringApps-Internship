import json
import os
import boto3

sns = boto3.client('sns')
SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']

def handler(event, context):
    print("Received SQS event:", json.dumps(event))
    
    for record in event['Records']:
        body = json.loads(record['body'])
        user_email = body.get('user_email', 'unknown-user@example.com')
        payload = body.get('payload', {})
        
        print(f"Processing payload: {payload} for user: {user_email}")
        
        email_message = f"Hello!\n\nYour async request has been successfully processed.\n\nPayload details:\n{json.dumps(payload, indent=2)}\n\nSent by: {user_email}"
        
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="Async Workflow Processing Complete",
            Message=email_message
        )
        print(f"Published SNS message for: {user_email}")
        
    return {
        'statusCode': 200,
        'body': json.dumps('Workflow completed successfully!')
    }
