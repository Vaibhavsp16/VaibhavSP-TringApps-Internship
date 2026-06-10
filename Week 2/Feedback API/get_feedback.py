import json
import boto3
import os
import base64
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ['TABLE_NAME']
ATTACHMENTS_BUCKET = os.environ['ATTACHMENTS_BUCKET']

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)
s3_client = boto3.client('s3')

def decode_jwt_payload(token):
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        payload_b64 += '=' * (4 - len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
        return json.loads(payload_json)
    except Exception as e:
        print(f"Error decoding JWT: {e}")
        return None

def lambda_handler(event, context):
    try:
        query_params = event.get('queryStringParameters') or {}
        is_download = query_params.get('download') == 'true'

        # Extract authorization header
        auth_header = None
        headers = event.get('headers') or {}
        for k, v in headers.items():
            if k.lower() == 'authorization':
                auth_header = v
                break

        logged_in_email = None
        is_admin = False

        if auth_header:
            token = auth_header[7:] if auth_header.lower().startswith('bearer ') else auth_header
            payload = decode_jwt_payload(token)
            if payload:
                logged_in_email = payload.get('email')
                role = payload.get('custom:role')
                if role == 'Admin' or logged_in_email == 'vaibhavsp16@gmail.com':
                    is_admin = True

        # Determine if we need to scan/query all items
        if is_download or logged_in_email:
            items = []
            exclusive_start_key = None
            while True:
                query_kwargs = {
                    'KeyConditionExpression': Key('type').eq('FEEDBACK'),
                    'ScanIndexForward': False
                }
                if exclusive_start_key:
                    query_kwargs['ExclusiveStartKey'] = exclusive_start_key
                
                response = table.query(**query_kwargs)
                items.extend(response.get('Items', []))
                
                exclusive_start_key = response.get('LastEvaluatedKey')
                if not exclusive_start_key:
                    break
        else:
            response = table.query(
                KeyConditionExpression=Key('type').eq('FEEDBACK'),
                ScanIndexForward=False,
                Limit=10
            )
            items = response.get('Items', [])

        # Filter by user if logged in and not admin
        if logged_in_email and not is_admin:
            items = [item for item in items if item.get('username') == logged_in_email]

        # Slice to 10 if not downloading
        if not is_download:
            items = items[:10]

        # Generate presigned GET URLs for items with file_keys (or legacy file_key)
        for item in items:
            keys = item.get('file_keys', [])
            if item.get('file_key') and item['file_key'] not in keys:
                keys = list(keys) + [item['file_key']]

            attachments = []
            if keys:
                for key in keys:
                    try:
                        get_url = s3_client.generate_presigned_url(
                            'get_object',
                            Params={
                                'Bucket': ATTACHMENTS_BUCKET,
                                'Key': key
                            },
                            ExpiresIn=3600  # 1 hour
                        )
                        attachments.append({
                            'key': key,
                            'url': get_url
                        })
                    except Exception as e:
                        print(f"Error generating presigned GET URL for key {key}: {e}")

            item['attachments'] = attachments

        response_headers = {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        }

        if is_download:
            response_headers['Content-Disposition'] = 'attachment; filename="student_feedback.json"'

        return {
            'statusCode': 200,
            'headers': response_headers,
            'body': json.dumps(items)
        }
    except Exception as e:
        print(f"Error retrieving feedback: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Internal server error processing request'})
        }