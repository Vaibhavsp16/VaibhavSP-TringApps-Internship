import os
import pymysql

def view_images():
    conn = pymysql.connect(
        host="img-pipeline-db-dev.c6bc6mig0igb.us-east-1.rds.amazonaws.com",
        user="admin",
        password=os.environ.get("DB_PASSWORD", "admin123"),
        database="image_pipeline",
        cursorclass=pymysql.cursors.DictCursor
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT image_id, user_id, original_name, status, created_at FROM images ORDER BY created_at DESC LIMIT 20")
            rows = cursor.fetchall()
            print("--- Database Content (images table) ---")
            for row in rows:
                print(f"ID: {row['image_id']} | User: {row['user_id']} | File: {row['original_name']} | Status: {row['status']} | Created: {row['created_at']}")
    finally:
        conn.close()

if __name__ == "__main__":
    view_images()
