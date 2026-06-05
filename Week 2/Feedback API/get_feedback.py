import json
import boto3
import os
from decimal import Decimal
from boto3.dynamodb.conditions import Key

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

TABLE_NAME = os.environ['TABLE_NAME']

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

def lambda_handler(event, context):
    try:
        response = table.query(
            KeyConditionExpression = Key('type').eq('FEEDBACK'),
            ScanIndexForward = False
        )

        items = response.get('Items', [])

        query_params = event.get('queryStringParameters') or {}
        is_download = query_params.get('download') == 'true'

        headers = {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        }

        if is_download:
            headers['Content-Disposition'] = 'attachment; filename="student_feedback.json"'

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps(items, cls=DecimalEncoder)
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