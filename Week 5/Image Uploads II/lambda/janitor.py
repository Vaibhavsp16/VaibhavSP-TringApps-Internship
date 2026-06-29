import json
import os
import boto3
import pymysql
import redis
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
sqs = boto3.client('sqs')

UPLOAD_BUCKET = os.environ['UPLOAD_BUCKET']
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
    print("Running scheduled database janitor & reconciliation loop...")
    
    conn = get_db_connection()
    r = get_redis_client()
    
    try:
        with conn.cursor() as cursor:
            sql = """
            SELECT image_id, user_id, original_name, s3_raw_key 
            FROM images 
            WHERE status = 'PENDING' AND created_at < NOW() - INTERVAL 5 MINUTE
            """
            cursor.execute(sql)
            stuck_images = cursor.fetchall()
            
        print(f"Found {len(stuck_images)} uploads stuck in PENDING state.")
        
        for record in stuck_images:
            image_id = record['image_id']
            user_id = record['user_id']
            s3_key = record['s3_raw_key']
            
            object_exists = False
            file_size = 0
            uploader_sub = user_id
            uploader_email = 'unknown-user@example.com'
            try:
                head = s3.head_object(Bucket=UPLOAD_BUCKET, Key=s3_key)
                object_exists = True
                file_size = head.get('ContentLength', 0)
                metadata = head.get('Metadata', {})
                uploader_sub = metadata.get('uploader-sub', user_id)
                uploader_email = metadata.get('uploader-email', 'unknown-user@example.com')
                print(f"Reconciliation: File {s3_key} exists in S3 bucket.")
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    print(f"Reconciliation: File {s3_key} does NOT exist in S3.")
                else:
                    print(f"S3 connection error checking {s3_key}: {str(e)}")
                    continue
            
            if object_exists:
                with conn.cursor() as cursor:
                    sql_update = """
                    UPDATE images 
                    SET status = 'EXTRACTED', file_size_bytes = %s, updated_at = NOW() 
                    WHERE image_id = %s
                    """
                    cursor.execute(sql_update, (file_size, image_id))
                conn.commit()
                
                message_body = {
                    "image_id": image_id,
                    "bucket": UPLOAD_BUCKET,
                    "key": s3_key,
                    "uploader_sub": uploader_sub,
                    "uploader_email": uploader_email,
                    "labels": [{"Name": "Recovered by Janitor", "Confidence": 100.0}],
                    "file_size": f"{round(file_size / 1024, 2)} KB" if file_size else "Unknown",
                    "upload_time": "Recovered"
                }
                sqs.send_message(
                    QueueUrl=QUEUE_URL,
                    MessageBody=json.dumps(message_body)
                )
                print(f"Recovered stuck upload: {image_id}. Triggered SQS processing.")
            else:
                with conn.cursor() as cursor:
                    sql_fail = """
                    UPDATE images 
                    SET status = 'FAILED', updated_at = NOW() 
                    WHERE image_id = %s
                    """
                    cursor.execute(sql_fail, (image_id,))
                conn.commit()
                print(f"Marked failed upload as FAILED: {image_id}")
            
            try:
                r.delete(f"user:history:{user_id}")
                print(f"Invalidated Redis cache for user: {user_id}")
            except Exception as cache_err:
                print(f"Redis cache delete failed: {str(cache_err)}")
                
    except Exception as e:
        print(f"Janitor loop encountered critical error: {str(e)}")
        raise e
    finally:
        conn.close()
        
    return {
        'statusCode': 200,
        'body': json.dumps('Janitor reconciliation completed successfully.')
    }
