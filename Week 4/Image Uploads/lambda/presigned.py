import json
import os
import boto3
import uuid
from botocore.config import Config

s3 = boto3.client(
    's3', 
    region_name=os.environ['AWS_REGION'], 
    config=Config(signature_version='s3v4')
)
BUCKET_NAME = os.environ['UPLOAD_BUCKET']

def handler(event, context):
    print("Received event:", json.dumps(event))
    
    body = event.get('body') or '{}'
    try:
        payload = json.loads(body)
    except Exception:
        payload = {}
        
    file_name = payload.get('filename')
    content_type = payload.get('contentType', 'image/jpeg')
    
    if not file_name:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'filename is required'})
        }
        
    authorizer_claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
    user_email = authorizer_claims.get('email', 'unknown-user@example.com')
    
    unique_key = f"{uuid.uuid4()}-{file_name}"
    
    try:
        presigned_url = s3.generate_presigned_url(
            ClientMethod='put_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': unique_key,
                'ContentType': content_type,
                'Metadata': {
                    'uploader-email': user_email
                }
            },
            ExpiresIn=300
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'uploadUrl': presigned_url,
                'fileKey': unique_key,
                'uploaderEmail': user_email
            })
        }
    except Exception as e:
        print(f"Error generating URL: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to generate URL: {str(e)}'})
        }
