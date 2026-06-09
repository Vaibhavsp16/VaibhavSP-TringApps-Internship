import boto3
import urllib.parse
import os
import uuid
from datetime import datetime

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

table_name = os.environ.get('DYNAMODB_TABLE_NAME', 'FeedbackAPI_Table')
table = dynamodb.Table(table_name)

def lambda_handler(event, context):
    for record in event['Records']:
        bucket_name = record['s3']['bucket']['name']
        file_key = urllib.parse.unquote_plus(record['s3']['object']['key'])
        
        print(f"Intercepted upload event for key: {file_key}")
        
        try:
            s3_meta = s3_client.head_object(Bucket=bucket_name, Key=file_key)
            file_size = s3_meta['ContentLength']
            content_type = s3_meta['ContentType']
            
            record_id = str(uuid.uuid4())
            table.put_item(
                Item={
                    'feedback_id': record_id,
                    'username': 'AUTOMATED_S3_AGENT',
                    'feedback': f"File Logged: Name={file_key}, Type={content_type}, Weight={file_size} bytes",
                    'timestamp': datetime.utcnow().isoformat(),
                    'source_asset_uri': f"s3://{bucket_name}/{file_key}"
                }
            )
            print(f"Asset tracking record committed to database row entry with reference UUID: {record_id}")
            
        except Exception as err:
            print(f"Critical execution error tracking storage changes: {str(err)}")
            raise err