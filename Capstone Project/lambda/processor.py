import json
import os
import boto3
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
DEFAULT_LATENCY = Decimal(os.environ.get('LATENCY_THRESHOLD_MS', '250'))
DEFAULT_CPU = Decimal(os.environ.get('CPU_THRESHOLD_PCT', '90'))
DEFAULT_MEMORY = Decimal(os.environ.get('MEMORY_THRESHOLD_PCT', '95'))

DEVICE_THRESHOLDS = {
    "api-gateway-prod": {
        "latency": Decimal("250"),
        "cpu": Decimal("80"),
        "memory": Decimal("85")
    },
    "auth-service-pod": {
        "latency": Decimal("150"),
        "cpu": Decimal("90"),
        "memory": Decimal("90")
    },
    "pdf-generator-worker": {
        "latency": Decimal("500"),
        "cpu": Decimal("85"),
        "memory": Decimal("95")
    },
    "default": {
        "latency": DEFAULT_LATENCY,
        "cpu": DEFAULT_CPU,
        "memory": DEFAULT_MEMORY
    }
}

table = dynamodb.Table(TABLE_NAME)

def lambda_handler(event, context):
    print("Processor Lambda received SQS batch event:", json.dumps(event))
    
    for record in event['Records']:
        try:
            body = json.loads(record['body'])
            device_id = body.get('device_id')
            timestamp = body.get('timestamp') or datetime.utcnow().isoformat()
            
            latency = Decimal(str(body.get('latency', 0)))
            cpu = Decimal(str(body.get('cpu_utilization', 0)))
            memory = Decimal(str(body.get('memory_utilization', 0)))
            
            submitted_by = body.get('submitted_by', 'System Simulator')
            
            item = {
                'PK': f"SERVER#{device_id}",
                'SK': f"LOG#{timestamp}",
                'device_id': device_id,
                'timestamp': timestamp,
                'latency': latency,
                'cpu_utilization': cpu,
                'memory_utilization': memory,
                'submitted_by': submitted_by
            }
            table.put_item(Item=item)
            print(f"Committed telemetry log for server: {device_id} at {timestamp}")
            
            thresholds = DEVICE_THRESHOLDS.get(device_id, DEVICE_THRESHOLDS["default"])
            is_anomaly = False
            anomaly_reason = ""
            
            if latency > thresholds["latency"]:
                is_anomaly = True
                anomaly_reason = f"Latency Spike: {latency} ms (Threshold: {thresholds['latency']} ms)"
            elif cpu > thresholds["cpu"]:
                is_anomaly = True
                anomaly_reason = f"CPU Overload: {cpu}% (Threshold: {thresholds['cpu']}%)"
            elif memory > thresholds["memory"]:
                is_anomaly = True
                anomaly_reason = f"Memory Crash (OOM): {memory}% (Threshold: {thresholds['memory']}%)"

            if is_anomaly:
                msg = f"CRITICAL incident warning triggered on system element: {device_id}!\n\n"
                msg += f"Incident Details: {anomaly_reason}\n"
                msg += f"Logged Timestamp: {timestamp}\n"
                
                sns.publish(
                    TopicArn=SNS_TOPIC_ARN,
                    Subject="ALERT: ServerWatch Infrastructure Incident",
                    Message=msg
                )
                print(f"Published real-time SNS anomaly alert for server: {device_id}")

            report_date = timestamp.split('T')[0]
            
            gate_inc = Decimal('1') if (latency > thresholds["latency"]) else Decimal('0')
            cpu_inc = Decimal('1') if (cpu > thresholds["cpu"]) else Decimal('0')
            mem_inc = Decimal('1') if (memory > thresholds["memory"]) else Decimal('0')
            
            update_expr = "SET report_date = :rd, #ts = :ts ADD active_devices :devs, gateway_spikes_count :g, cpu_overloads_count :c, memory_crashes_count :m"
            expr_attr_values = {
                ":rd": report_date,
                ":ts": timestamp,
                ":devs": {device_id},
                ":g": gate_inc,
                ":c": cpu_inc,
                ":m": mem_inc
            }
            
            if is_anomaly:
                update_expr += ", anomaly_devices :a_devs"
                expr_attr_values[":a_devs"] = {device_id}
                
            table.update_item(
                Key={
                    'PK': "REPORT#DAILY",
                    'SK': f"DATE#{report_date}"
                },
                UpdateExpression=update_expr,
                ExpressionAttributeNames={
                    "#ts": "timestamp"
                },
                ExpressionAttributeValues=expr_attr_values
            )
            print(f"DynamoDB aggregate report updated for date: {report_date}")
            
        except Exception as e:
            print(f"Error processing record: {str(e)}")
            raise e
            
    return {
        'statusCode': 200,
        'body': json.dumps('Batch processed successfully')
    }
