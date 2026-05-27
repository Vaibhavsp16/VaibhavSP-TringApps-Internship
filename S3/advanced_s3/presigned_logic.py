import boto3
import requests
import hashlib
import base64
from botocore.exceptions import ClientError
from botocore.client import Config 

s3_client = boto3.client(
    's3', 
    region_name='us-east-1',
    config=Config(signature_version='s3v4')
)

BUCKET_NAME = 'vaibhav-s3-advanced-vault-1612'
OBJECT_NAME = 'presigned_test.txt'

with open('presigned_test.txt', 'rb') as f:
    file_content = f.read()

md5_hash = hashlib.md5(file_content).digest()
base64_md5 = base64.b64encode(md5_hash).decode('utf-8')

def create_presigned_put():
    try:
        return s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': BUCKET_NAME, 
                'Key': OBJECT_NAME,
                'ContentMD5': base64_md5 
            },
            ExpiresIn=300
        )
    except ClientError as e:
        print(e)
        return None

def create_presigned_get():
    try:
        return s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': OBJECT_NAME},
            ExpiresIn=300
        )
    except ClientError as e:
        print(e)
        return None

print("1. Generating PUT URL...")
upload_url = create_presigned_put()
print(f"URL: {upload_url}\n")

print("2. Simulating the Frontend Uploading data...")
headers = {'Content-MD5': base64_md5}
upload_response = requests.put(upload_url, data=file_content, headers=headers)

if upload_response.status_code != 200:
    print(f"Upload Failed. AWS Error: {upload_response.text}\n")
else:
    print(f"Upload Status Code: {upload_response.status_code} (Success!)\n")

print("3. Generating GET URL...")
download_url = create_presigned_get()
print(f"URL: {download_url}\n")
print(f"MD5 Hash for Postman: {base64_md5}")

print("4. Simulating the Frontend Downloading data...")
download_response = requests.get(download_url)
print(f"Downloaded Content: {download_response.text}")