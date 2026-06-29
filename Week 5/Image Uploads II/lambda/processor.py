import json
import os
import boto3
import pymysql
import redis

s3 = boto3.client('s3')
sns = boto3.client('sns')

PROCESSED_BUCKET = os.environ['PROCESSED_BUCKET']
SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']

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
    print("Received SQS event:", json.dumps(event))
    
    for record in event['Records']:
        body = json.loads(record['body'])
        image_id = body.get('image_id')
        upload_bucket = body['bucket']
        key = body['key']
        uploader_sub = body.get('uploader_sub', 'unknown-user-sub')
        uploader_email = body['uploader_email']
        labels = body['labels']
        file_size = body.get('file_size', 'Unknown')
        upload_time = body.get('upload_time', 'Unknown')
        
        print(f"Processing image {key} (ImageID: {image_id}) uploaded by {uploader_email} (Sub: {uploader_sub})")
        
        try:
            copy_source = {'Bucket': upload_bucket, 'Key': key}
            s3.copy_object(
                Bucket=PROCESSED_BUCKET,
                Key=key,
                CopySource=copy_source
            )
            print(f"Copied image {key} to processed bucket: {PROCESSED_BUCKET}")
            
            analysis_key = f"{key}-analysis.json"
            analysis_data = {
                "original_file": key,
                "uploader_email": uploader_email,
                "file_size": file_size,
                "upload_time": upload_time,
                "detected_labels": labels
            }
            s3.put_object(
                Bucket=PROCESSED_BUCKET,
                Key=analysis_key,
                Body=json.dumps(analysis_data, indent=2),
                ContentType='application/json'
            )
            print(f"Saved metadata sidecar: {analysis_key}")
            
            if image_id:
                conn = get_db_connection()
                try:
                    with conn.cursor() as cursor:
                        sql = """
                        UPDATE images 
                        SET status = 'COMPLETED', s3_processed_key = %s, updated_at = NOW() 
                        WHERE image_id = %s
                        """
                        cursor.execute(sql, (key, image_id))
                    conn.commit()
                    print(f"Updated status in RDS to COMPLETED for {image_id}")
                    
                    with conn.cursor() as cursor:
                        sql_select = """
                        SELECT image_id as id, original_name as fileName, file_size_bytes as fileSize, 
                               status, thumbnail_base64 as thumbnailData, created_at
                        FROM images 
                        WHERE user_id = %s 
                        ORDER BY created_at DESC 
                        LIMIT 5
                        """
                        cursor.execute(sql_select, (uploader_sub,))
                        rows = cursor.fetchall()
                        
                        history_data = []
                        for row in rows:
                            history_data.append({
                                "id": row["id"],
                                "fileName": row["fileName"],
                                "fileSize": str(row["fileSize"]) + " Bytes" if row["fileSize"] else "Unknown",
                                "status": row["status"],
                                "thumbnailData": row["thumbnailData"],
                                "timestamp": row["created_at"].strftime('%m/%d/%Y, %I:%M:%S %p UTC') if row["created_at"] else "Unknown"
                            })
                            
                        try:
                            r = get_redis_client()
                            r.set(f"user:history:{uploader_sub}", json.dumps(history_data), ex=3600)
                            print(f"Updated Redis cache for user: {uploader_sub}")
                        except Exception as cache_err:
                            print(f"Redis cache update failed (non-blocking): {str(cache_err)}")
                            
                except Exception as db_err:
                    print(f"Database operation failed: {str(db_err)}")
                finally:
                    conn.close()

            labels_summary = "\n".join([
                f"- {l['Name']} ({l['Confidence']:.2f}% confidence)"
                for l in labels
            ])
            
            email_body = (
                f"Hello!\n\n"
                f"Your image has been successfully processed by the AI pipeline.\n\n"
                f"--- Image Details ---\n"
                f"- File Name: {key}\n"
                f"- File Size: {file_size}\n"
                f"- Upload Time: {upload_time}\n\n"
                f"--- AI Image Recognition Labels ---\n"
                f"{labels_summary}\n\n"
                f"S3 Locations:\n"
                f"- Processed Image: s3://{PROCESSED_BUCKET}/{key}\n"
                f"- AI Metadata File: s3://{PROCESSED_BUCKET}/{analysis_key}\n\n"
                f"Regards,\nImage Pipeline"
            )
            
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject="Image Pipeline: AI Processing Complete",
                Message=email_body
            )
            print(f"Sent email notification to SNS for {uploader_email}")
            
        except Exception as e:
            print(f"Error processing file {key}: {str(e)}")
            if 'image_id' in locals() and image_id:
                try:
                    conn = get_db_connection()
                    with conn.cursor() as cursor:
                        sql_fail = """
                        UPDATE images 
                        SET status = 'FAILED', updated_at = NOW() 
                        WHERE image_id = %s
                        """
                        cursor.execute(sql_fail, (image_id,))
                    conn.commit()
                    print(f"Updated status in RDS to FAILED for {image_id}")
                    
                    try:
                        r = get_redis_client()
                        r.delete(f"user:history:{uploader_sub}")
                    except Exception as cache_err:
                        print(f"Redis cache delete failed: {str(cache_err)}")
                except Exception as db_err:
                    print(f"Failed to update database status to FAILED: {str(db_err)}")
                finally:
                    if 'conn' in locals() and conn:
                        conn.close()
            raise e
            
    return {
        'statusCode': 200,
        'body': json.dumps('Finished SQS queue record processing.')
    }
