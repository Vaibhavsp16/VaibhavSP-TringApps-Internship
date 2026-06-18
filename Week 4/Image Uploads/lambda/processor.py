import json
import os
import boto3

s3 = boto3.client('s3')
sns = boto3.client('sns')

PROCESSED_BUCKET = os.environ['PROCESSED_BUCKET']
SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']

def handler(event, context):
    print("Received SQS event:", json.dumps(event))
    
    for record in event['Records']:
        body = json.loads(record['body'])
        upload_bucket = body['bucket']
        key = body['key']
        uploader_email = body['uploader_email']
        labels = body['labels']
        
        print(f"Processing image {key} uploaded by {uploader_email}")
        
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
                "detected_labels": labels
            }
            s3.put_object(
                Bucket=PROCESSED_BUCKET,
                Key=analysis_key,
                Body=json.dumps(analysis_data, indent=2),
                ContentType='application/json'
            )
            print(f"Saved metadata sidecar: {analysis_key}")
            
            labels_summary = "\n".join([
                f"- {l['Name']} ({l['Confidence']:.2f}% confidence)"
                for l in labels
            ])
            
            email_body = (
                f"Hello!\n\n"
                f"Your image '{key}' has been processed by the AI pipeline.\n\n"
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
            raise e
            
    return {
        'statusCode': 200,
        'body': json.dumps('Finished SQS queue record processing.')
    }
