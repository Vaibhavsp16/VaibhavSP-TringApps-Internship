import boto3

# 1. Initialize the S3 client
# Boto3 automatically finds the AWS credentials you set up yesterday!
s3 = boto3.client('s3')

# 2. Define your variables
bucket_name = 'vaibhav-s3-bucket-1612'
local_file = 'my_data.csv'
s3_file_name = 'my_data_via_python.csv' # Giving it a slightly different name so we can spot it!

print(f"Uploading {local_file} to S3...")

# 3. Execute the upload
try:
    # Syntax: upload_file(local_file_path, bucket_name, destination_key)
    s3.upload_file(local_file, bucket_name, s3_file_name)
    print(f"Success! 🚀 {s3_file_name} is now in your secure bucket.")
except Exception as e:
    print(f"Uh oh, something went wrong: {e}")