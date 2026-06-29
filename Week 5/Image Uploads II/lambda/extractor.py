import json
import os
import boto3
import urllib.parse
import math
import pymysql
import redis

s3 = boto3.client('s3')
rekognition = boto3.client('rekognition')
sqs = boto3.client('sqs')

QUEUE_URL = os.environ['QUEUE_URL']

def get_db_connection():
    return pymysql.connect(
        host=os.environ['DB_HOST'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        database=os.environ['DB_NAME'],
        connect_timeout=5,
        cursorclass=pymysql.cursors.DictCursor
    )

def get_redis_client():
    return redis.Redis(
        host=os.environ['REDIS_HOST'],
        port=int(os.environ.get('REDIS_PORT', 6379)),
        db=0,
        socket_timeout=3,
        decode_responses=True
    )

def handler(event, context):
    print("Received S3 event:", json.dumps(event))
    
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(record['s3']['object']['key'])
        
        try:
            s3_metadata = s3.head_object(Bucket=bucket, Key=key)
            metadata = s3_metadata.get('Metadata', {})
            uploader_sub = metadata.get('uploader-sub', 'unknown-user-sub')
            uploader_email = metadata.get('uploader-email', 'unknown-user@example.com')
            image_id = metadata.get('image-id')
            
            if not image_id:
                try:
                    image_id = key.split('-')[0]
                    if len(image_id) != 36:
                        image_id = None
                except Exception:
                    image_id = None
            
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
            
            print(f"File {key} (ImageID: {image_id}) uploaded by: {uploader_email} | Size: {file_size_str}")
            
            if image_id:
                conn = get_db_connection()
                try:
                    with conn.cursor() as cursor:
                        sql = """
                        UPDATE images 
                        SET status = 'EXTRACTED', file_size_bytes = %s, updated_at = NOW() 
                        WHERE image_id = %s
                        """
                        cursor.execute(sql, (content_length, image_id))
                    conn.commit()
                    print(f"Updated status in RDS to EXTRACTED for {image_id}")
                except Exception as db_err:
                    print(f"Database update failed: {str(db_err)}")
                finally:
                    conn.close()

            try:
                r = get_redis_client()
                r.delete(f"user:history:{uploader_sub}")
            except Exception as cache_err:
                print(f"Redis cache invalidation failed (non-blocking): {str(cache_err)}")

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
                "image_id": image_id,
                "bucket": bucket,
                "key": key,
                "uploader_sub": uploader_sub,
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
