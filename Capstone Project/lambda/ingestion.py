import json
import os
import boto3

sqs = boto3.client('sqs')
QUEUE_URL = os.environ.get('QUEUE_URL')

def lambda_handler(event, context):
    print("Ingestion Lambda received event:", json.dumps(event))
    
    body_str = event.get('body') or '{}'
    try:
        body = json.loads(body_str)
    except Exception as e:
        return response(400, {"error": "Invalid JSON format in body"})
        
    device_id = body.get('device_id')
    latency = body.get('latency')
    cpu = body.get('cpu_utilization')
    memory = body.get('memory_utilization')
    
    if not device_id or latency is None or cpu is None or memory is None:
        return response(400, {"error": "device_id, latency, cpu_utilization, and memory_utilization are required fields"})
        
    payload = {
        "device_id": device_id,
        "latency": float(latency),
        "cpu_utilization": float(cpu),
        "memory_utilization": float(memory),
        "timestamp": body.get('timestamp') or context.aws_request_id,
        "submitted_by": body.get('submitted_by') or 'System Simulator'
    }
    
    try:
        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(payload)
        )
        return response(202, {
            "message": "Telemetry reading successfully received and queued",
            "device_id": device_id
        })
    except Exception as e:
        print(f"Error sending message to SQS: {str(e)}")
        return response(500, {"error": "Failed to queue telemetry log"})

def response(status_code, body_dict):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body_dict)
    }
