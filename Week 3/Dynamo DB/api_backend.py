import boto3
import json
import os
import uuid
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('DYNAMODB_TABLE_NAME', 'FeedbackAPI_Table')
table = dynamodb.Table(table_name)

def lambda_handler(event, context):
    http_method = event.get('httpMethod')
    print(f"Received request with HTTP method: {http_method}")
    
    try:
        if http_method == 'POST':
            if not event.get('body'):
                return build_response(400, {"error": "Missing request body"})
            
            body = json.loads(event['body'])
            new_id = str(uuid.uuid4())
            
            table.put_item(
                Item={
                    'feedback_id': new_id,
                    'username': body.get('username', 'Anonymous'),
                    'feedback': body.get('feedback', ''),
                    'timestamp': datetime.utcnow().isoformat()
                }
            )
            return build_response(201, {"message": "Feedback created successfully", "id": new_id})

        elif http_method == 'GET':
            query_params = event.get('queryStringParameters')
            if not query_params or 'id' not in query_params:
                return build_response(400, {"error": "Missing required query string parameter 'id'"})
            
            feedback_id = query_params['id']
            response = table.get_item(Key={'feedback_id': feedback_id})
            
            if 'Item' in response:
                return build_response(200, response['Item'])
                
            return build_response(404, {"message": f"Feedback record {feedback_id} not found"})

        elif http_method == 'DELETE':
            if not event.get('body'):
                return build_response(400, {"error": "Missing request body"})
                
            body = json.loads(event['body'])
            if 'id' not in body:
                return build_response(400, {"error": "Missing target 'id' in request body"})
                
            table.delete_item(Key={'feedback_id': body['id']})
            return build_response(200, {"message": f"Feedback record {body['id']} deleted successfully"})

        else:
            return build_response(405, {"message": f"Method {http_method} not supported"})

    except Exception as e:
        print(f"Execution Error: {str(e)}")
        return build_response(500, {"error": "Internal Server Error", "details": str(e)})


def build_response(status_code, body_dict):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body_dict)
    }