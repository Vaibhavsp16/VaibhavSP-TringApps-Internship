import json
import os
import boto3
import urllib.parse

# Initialize clients
s3 = boto3.client('s3')
rekognition = boto3.client('rekognition')
sqs = boto3.client('sqs')

QUEUE_URL = os.environ['QUEUE_URL']

def handler(event, context):
    print("Received S3 event:", json.dumps(event))
    
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        # S3 event keys are URL-encoded; we must decode them to query boto3 correctly
        key = urllib.parse.unquote_plus(record['s3']['object']['key'])
        
        try:
            s3_metadata = s3.head_object(Bucket=bucket, Key=key)
            metadata = s3_metadata.get('Metadata', {})
            uploader_email = metadata.get('uploader-email', 'unknown-user@example.com')
            
            print(f"File {key} uploaded by: {uploader_email}")
            
            rek_response = rekognition.detect_labels(
                Image={
                    'S3Object': {
                        'Bucket': bucket,
                        'Name': key
                    }
                },
                MaxLabels=5,     
                MinConfidence=75.0 
            )
            
            labels = [
                {"Name": label['Name'], "Confidence": label['Confidence']}
                for label in rek_response.get('Labels', [])
            ]
            print(f"AI Labels detected: {labels}")
            
            message_body = {
                "bucket": bucket,
                "key": key,
                "uploader_email": uploader_email,
                "labels": labels
            }
            
            sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps(message_body)
            )
            print("Successfully forwarded metadata message to SQS Queue.")
            
        except Exception as e:
            print(f"Error processing S3 object {key}: {str(e)}")
            raise e
            
    return {
        'statusCode': 200,
        'body': json.dumps('AI Extraction Completed!')
    }
