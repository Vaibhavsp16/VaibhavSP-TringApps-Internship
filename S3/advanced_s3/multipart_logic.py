import boto3
from boto3.s3.transfer import TransferConfig
import os

s3_client = boto3.client('s3', region_name='us-east-1')
BUCKET_NAME = 'vaibhav-s3-advanced-vault-1612'
FILE_NAME = 'massive_dataset.csv'

multipart_config = TransferConfig(multipart_threshold=8 * 1024 * 1024, 
                                  max_concurrency=10,
                                  multipart_chunksize=8 * 1024 * 1024,
                                  use_threads=True
)

print("Generating a test file.... this might take a second.")
with open(FILE_NAME, 'wb') as f:
    f.write(os.urandom(10 * 1024 * 1024))

print("Starting multipart upload...")
try:
    s3_client.upload_file(Filename=FILE_NAME, 
                          Bucket=BUCKET_NAME, 
                          Key=FILE_NAME, 
                          Config=multipart_config
    )
    print("Multipart upload completed successfully!")
except Exception as e:
    print(f"Upload Failed: {e}")