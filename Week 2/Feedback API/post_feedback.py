import json
import boto3
import os
import datetime
import uuid

BUCKET_NAME = os.environ['BUCKET_NAME']
s3_client = boto3.client('s3')

def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        feedback_text = body.get('feedback')

        request_context = event.get('requestContext') or {}
        authorizer = request_context.get('authorizer') or {}
        claims = authorizer.get('claims') or {}
        username = body.get('username') or claims.get('email', 'Anonymous')

        if not feedback_text:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Feedback text is required'})
            }
        
        timestamp = datetime.datetime.utcnow().isoformat()
        feedback_id = str(uuid.uuid4())

        item = {
            'timestamp': timestamp,
            'feedback_id': feedback_id,
            'username': username,
            'feedback': feedback_text
        }

        if username == 'vaibhavsp16@gmail.com' and 'encrypted_token' in body:
            item['encrypted_token'] = body['encrypted_token']

        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=f"feedback/{timestamp}_{feedback_id}.json",
            Body=json.dumps(item),
            ContentType='application/json'
        )

        return {
            'statusCode': 201,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'message': 'Feedback submitted successfully'})
        }
    except Exception as e:
        print(f"Error saving feedback: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Internal server error processing request'})
        }