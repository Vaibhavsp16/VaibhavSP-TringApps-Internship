import json
import os
import boto3
import urllib.parse
import math

s3 = boto3.client('s3')
rekognition = boto3.client('rekognition')
sqs = boto3.client('sqs')

QUEUE_URL = os.environ['QUEUE_URL']

def handler(event, context):
    print("Received S3 event:", json.dumps(event))
    
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(record['s3']['object']['key'])
        
        try:
            s3_metadata = s3.head_object(Bucket=bucket, Key=key)
            metadata = s3_metadata.get('Metadata', {})
            uploader_email = metadata.get('uploader-email', 'unknown-user@example.com')
            
            content_length = s3_metadata.get('ContentLength', 0)
            last_modified = s3_metadata.get('LastModified')
            
            if content_length == 0:
                file_size_str = "0 Bytes"
            else:
                try:
                    k = 1024
                    sizes = ['Bytes', 'KB', 'MB', 'GB']
                    i = int(math.floor(math.log(content_length) / math.log(k)))
                    file_size_str = f"{round(content_length / (k ** i), 2)} {sizes[i]}"
                except Exception:
                    file_size_str = f"{content_length} Bytes"
            
            if last_modified:
                upload_time_str = last_modified.strftime('%m/%d/%Y, %I:%M:%S %p UTC')
            else:
                upload_time_str = 'Unknown'
            
            print(f"File {key} uploaded by: {uploader_email} | Size: {file_size_str} | Time: {upload_time_str}")
            
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
                "labels": labels,
                "file_size": file_size_str,
                "upload_time": upload_time_str
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
