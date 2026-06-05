import json
import boto3
import os
import datetime
import uuid

TABLE_NAME = os.environ['TABLE_NAME']

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

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

        table.put_item(
            Item={
                'type': 'FEEDBACK',
                'timestamp': timestamp,
                'feedback_id': str(uuid.uuid4()),
                'username': username,
                'feedback': feedback_text
            }
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