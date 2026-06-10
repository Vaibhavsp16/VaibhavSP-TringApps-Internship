import json
import boto3
import os
import datetime
import uuid
import base64

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
        http_method = event.get('httpMethod', 'POST')
        body = json.loads(event.get('body', '{}'))

        path = event.get('path', '')
        resource_path = event.get('resource', '')

        # 1. Handle GET Upload URL Request (POST /feedback/upload-url)
        if path.endswith('/upload-url') or resource_path.endswith('/upload-url'):
            if http_method != 'POST':
                return response(405, {'error': f'Method {http_method} not allowed on upload-url'})
            
            filename = body.get('filename')
            content_type = body.get('contentType')

            if not filename or not content_type:
                return response(400, {'error': 'filename and contentType are required'})

            # Generate a unique key for S3
            file_extension = os.path.splitext(filename)[1]
            unique_id = str(uuid.uuid4())
            file_key = f"uploads/{unique_id}{file_extension}"

            try:
                upload_url = s3_client.generate_presigned_url(
                    'put_object',
                    Params={
                        'Bucket': ATTACHMENTS_BUCKET,
                        'Key': file_key,
                        'ContentType': content_type
                    },
                    ExpiresIn=300  # 5 minutes
                )
                return response(200, {
                    'upload_url': upload_url,
                    'file_key': file_key
                })
            except Exception as e:
                print(f"Error generating presigned upload URL: {str(e)}")
                return response(500, {'error': 'Error generating presigned upload URL'})

        # Standard /feedback routes
        request_context = event.get('requestContext') or {}
        authorizer = request_context.get('authorizer') or {}
        claims = authorizer.get('claims') or {}

        # Extract authorization token for manual claim parsing
        auth_header = None
        headers = event.get('headers') or {}
        for k, v in headers.items():
            if k.lower() == 'authorization':
                auth_header = v
                break

        logged_in_email = claims.get('email')
        is_admin = claims.get('custom:role') == 'Admin' or logged_in_email == 'vaibhavsp16@gmail.com'

        if auth_header and not logged_in_email:
            token = auth_header[7:] if auth_header.lower().startswith('bearer ') else auth_header
            payload = decode_jwt_payload(token)
            if payload:
                logged_in_email = payload.get('email')
                role = payload.get('custom:role')
                if role == 'Admin' or logged_in_email == 'vaibhavsp16@gmail.com':
                    is_admin = True

        if http_method == 'POST':
            feedback_text = body.get('feedback')
            username = body.get('username') or logged_in_email or 'Anonymous'

            if not feedback_text:
                return response(400, {'error': 'Feedback text is required'})
            
            timestamp = datetime.datetime.utcnow().isoformat()
            feedback_id = str(uuid.uuid4())

            item = {
                'type': 'FEEDBACK',
                'timestamp': timestamp,
                'feedback_id': feedback_id,
                'username': username,
                'feedback': feedback_text
            }

            if body.get('file_keys'):
                item['file_keys'] = body['file_keys']
            elif body.get('file_key'):
                item['file_keys'] = [body['file_key']]

            if username == 'vaibhavsp16@gmail.com' and 'encrypted_token' in body:
                item['encrypted_token'] = body['encrypted_token']

            table.put_item(Item=item)
            return response(201, {'message': 'Feedback submitted successfully'})

        elif http_method == 'PUT':
            timestamp = body.get('timestamp')
            feedback_text = body.get('feedback')

            if not timestamp or not feedback_text:
                return response(400, {'error': 'Timestamp and feedback text are required'})

            if not logged_in_email:
                return response(401, {'error': 'Unauthorized'})

            # Retrieve existing item
            resp = table.get_item(Key={'type': 'FEEDBACK', 'timestamp': timestamp})
            existing_item = resp.get('Item')

            if not existing_item:
                return response(404, {'error': 'Feedback not found'})

            # Verify ownership: Only the creator can edit their feedback
            if existing_item.get('username') != logged_in_email:
                return response(403, {'error': 'Forbidden: You can only edit your own feedback'})

            # Retained and new keys from client
            new_file_keys = body.get('file_keys', [])

            # Get old keys (including legacy file_key)
            existing_keys = existing_item.get('file_keys', [])
            if existing_item.get('file_key') and existing_item['file_key'] not in existing_keys:
                existing_keys = list(existing_keys) + [existing_item['file_key']]

            # Keys to delete from S3 (existed before but not anymore)
            deleted_keys = set(existing_keys) - set(new_file_keys)

            for key in deleted_keys:
                try:
                    s3_client.delete_object(Bucket=ATTACHMENTS_BUCKET, Key=key)
                except Exception as s3_err:
                    print(f"Error deleting S3 object on edit: {s3_err}")

            # Construct DynamoDB updates
            expr_vals = {':f': feedback_text}
            
            remove_clause = ""
            if 'file_key' in existing_item:
                remove_clause = " REMOVE file_key"

            if new_file_keys:
                update_expr = f"SET feedback = :f, file_keys = :fks"
                if remove_clause:
                    update_expr += remove_clause
                expr_vals[':fks'] = new_file_keys
            else:
                update_expr = f"SET feedback = :f REMOVE file_keys"
                if remove_clause:
                    update_expr += ", file_key"

            table.update_item(
                Key={'type': 'FEEDBACK', 'timestamp': timestamp},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_vals
            )
            return response(200, {'message': 'Feedback updated successfully'})

        elif http_method == 'DELETE':
            timestamp = body.get('timestamp')

            if not timestamp:
                return response(400, {'error': 'Timestamp is required'})

            if not logged_in_email:
                return response(401, {'error': 'Unauthorized'})

            # Retrieve existing item
            resp = table.get_item(Key={'type': 'FEEDBACK', 'timestamp': timestamp})
            existing_item = resp.get('Item')

            if not existing_item:
                return response(404, {'error': 'Feedback not found'})

            # Verify ownership/permissions:
            if not is_admin and existing_item.get('username') != logged_in_email:
                return response(403, {'error': 'Forbidden: You can only delete your own feedback'})

            # Clean up all S3 objects first
            keys = existing_item.get('file_keys', [])
            if existing_item.get('file_key') and existing_item['file_key'] not in keys:
                keys = list(keys) + [existing_item['file_key']]

            if keys:
                for key in keys:
                    try:
                        s3_client.delete_object(Bucket=ATTACHMENTS_BUCKET, Key=key)
                    except Exception as s3_err:
                        print(f"Error deleting S3 object on delete: {s3_err}")

            # Perform delete in DynamoDB
            table.delete_item(Key={'type': 'FEEDBACK', 'timestamp': timestamp})
            return response(200, {'message': 'Feedback deleted successfully'})

        else:
            return response(405, {'error': f'Method {http_method} not allowed'})

    except Exception as e:
        print(f"Error processing feedback request: {str(e)}")
        return response(500, {'error': 'Internal server error processing request'})

def response(status_code, body_dict):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body_dict)
    }