import json
import boto3
import os
import concurrent.futures

BUCKET_NAME = os.environ['BUCKET_NAME']
s3_client = boto3.client('s3')

def fetch_object(key):
    try:
        resp = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
        content = resp['Body'].read().decode('utf-8')
        return json.loads(content)
    except Exception as e:
        print(f"Error fetching key {key}: {e}")
        return None

def lambda_handler(event, context):
    try:
        query_params = event.get('queryStringParameters') or {}
        is_download = query_params.get('download') == 'true'

        keys = []
        continuation_token = None
        while True:
            kwargs = {'Bucket': BUCKET_NAME, 'Prefix': 'feedback/'}
            if continuation_token:
                kwargs['ContinuationToken'] = continuation_token
            
            resp = s3_client.list_objects_v2(**kwargs)
            contents = resp.get('Contents', [])
            for obj in contents:
                key = obj['Key']
                if key.startswith('feedback/') and key.endswith('.json'):
                    keys.append(key)
            
            if resp.get('IsTruncated'):
                continuation_token = resp.get('NextContinuationToken')
            else:
                break

        keys.sort(reverse=True)

        target_keys = keys if is_download else keys[:10]

        items = []
        if target_keys:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                results = list(executor.map(fetch_object, target_keys))
            items = [item for item in results if item is not None]

        headers = {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        }

        if is_download:
            headers['Content-Disposition'] = 'attachment; filename="student_feedback.json"'

        return {
            'statusCode': 200,
            'headers': headers,
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