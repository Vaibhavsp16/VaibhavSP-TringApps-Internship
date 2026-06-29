import json
import os
import boto3
import uuid
import pymysql
import redis
from botocore.config import Config

s3 = boto3.client(
    's3', 
    region_name=os.environ['AWS_REGION'], 
    config=Config(signature_version='s3v4')
)
BUCKET_NAME = os.environ['UPLOAD_BUCKET']

def init_db(conn):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                image_id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(100) NOT NULL,
                original_name VARCHAR(255) NOT NULL,
                s3_raw_key VARCHAR(255) NOT NULL,
                s3_processed_key VARCHAR(255),
                file_size_bytes BIGINT,
                status VARCHAR(20) NOT NULL,
                thumbnail_base64 MEDIUMTEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_user_created (user_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
        conn.commit()
        print("Database schema initialized successfully.")
    except Exception as e:
        print(f"Error initializing DB schema: {str(e)}")

def get_db_connection():
    conn = pymysql.connect(
        host=os.environ['DB_HOST'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        database=os.environ['DB_NAME'],
        connect_timeout=5,
        cursorclass=pymysql.cursors.DictCursor
    )
    init_db(conn)
    return conn

def get_redis_client():
    return redis.Redis(
        host=os.environ['REDIS_HOST'],
        port=int(os.environ.get('REDIS_PORT', 6379)),
        db=0,
        socket_timeout=3,
        decode_responses=True
    )

def handler(event, context):
    print("Received event:", json.dumps(event))
    
    body = event.get('body') or '{}'
    try:
        payload = json.loads(body)
    except Exception:
        payload = {}
        
    file_name = payload.get('filename')
    content_type = payload.get('contentType', 'image/jpeg')
    thumbnail_base64 = payload.get('thumbnail')
    
    if not file_name:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'filename is required'})
        }
        
    authorizer_claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
    user_sub = authorizer_claims.get('sub', 'unknown-user-sub')
    user_email = authorizer_claims.get('email', 'unknown-user@example.com')
    
    image_id = str(uuid.uuid4())
    unique_key = f"{image_id}-{file_name}"
    
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO images (image_id, user_id, original_name, s3_raw_key, status, thumbnail_base64, created_at, updated_at)
                VALUES (%s, %s, %s, %s, 'PENDING', %s, NOW(), NOW())
                """
                cursor.execute(sql, (image_id, user_sub, file_name, unique_key, thumbnail_base64))
            conn.commit()
            print(f"Created pending record in RDS for {image_id}")
        finally:
            conn.close()
            
        try:
            r = get_redis_client()
            r.delete(f"user:history:{user_sub}")
            print(f"Invalidated Redis cache for user: {user_sub}")
        except Exception as cache_err:
            print(f"Redis cache invalidation failed (non-blocking): {str(cache_err)}")

        presigned_url = s3.generate_presigned_url(
            ClientMethod='put_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': unique_key,
                'ContentType': content_type,
                'Metadata': {
                    'uploader-sub': user_sub,
                    'uploader-email': user_email,
                    'image-id': image_id
                }
            },
            ExpiresIn=300
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization'
            },
            'body': json.dumps({
                'uploadUrl': presigned_url,
                'fileKey': unique_key,
                'imageId': image_id,
                'uploaderEmail': user_email,
                'uploaderSub': user_sub
            })
        }
    except Exception as e:
        print(f"Error in presigned handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to process upload request: {str(e)}'})
        }
