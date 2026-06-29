import json
import os
import pymysql
import redis

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
    print("Received history request event:", json.dumps(event))
    
    authorizer_claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
    user_sub = authorizer_claims.get('sub')
    
    if not user_sub:
        return {
            'statusCode': 401,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Unauthorized: Cognito subject claim is missing'})
        }

    history_list = []
    cache_hit = False

    try:
        r = get_redis_client()
        cache_key = f"user:history:{user_sub}"
        cached_data = r.get(cache_key)
        if cached_data:
            history_list = json.loads(cached_data)
            cache_hit = True
            print(f"Redis Cache HIT for user: {user_sub}")
    except Exception as cache_err:
        print(f"Redis lookup failed (falling back to database): {str(cache_err)}")

    if not cache_hit:
        print(f"Redis Cache MISS for user: {user_sub}. Fetching from RDS...")
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    sql = """
                    SELECT image_id as id, original_name as fileName, file_size_bytes as fileSize, 
                           status, thumbnail_base64 as thumbnailData, created_at
                    FROM images 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT 5
                    """
                    cursor.execute(sql, (user_sub,))
                    rows = cursor.fetchall()
                    
                    for row in rows:
                        history_list.append({
                            "id": row["id"],
                            "fileName": row["fileName"],
                            "fileSize": str(row["fileSize"]) + " Bytes" if row["fileSize"] else "Unknown",
                            "status": row["status"],
                            "thumbnailData": row["thumbnailData"],
                            "timestamp": row["created_at"].strftime('%m/%d/%Y, %I:%M:%S %p UTC') if row["created_at"] else "Unknown"
                        })
                
                try:
                    r = get_redis_client()
                    r.set(cache_key, json.dumps(history_list), ex=3600)
                    print(f"Updated Redis cache for user: {user_sub}")
                except Exception as cache_err:
                    print(f"Redis cache update failed (non-blocking): {str(cache_err)}")
                    
            finally:
                conn.close()
        except Exception as db_err:
            print(f"Database query failed: {str(db_err)}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': f'Failed to retrieve upload history: {str(db_err)}'})
            }

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization'
        },
        'body': json.dumps(history_list)
    }
