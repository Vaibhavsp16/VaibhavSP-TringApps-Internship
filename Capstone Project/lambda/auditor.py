import json
import os
import decimal
import boto3
from datetime import datetime
from boto3.dynamodb.conditions import Key

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            if o % 1 > 0:
                return float(o)
            else:
                return int(o)
        return super(DecimalEncoder, self).default(o)

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')

DEVICE_THRESHOLDS = {
    "api-gateway-prod": {
        "latency": 250.0,
        "cpu": 80.0,
        "memory": 85.0
    },
    "auth-service-pod": {
        "latency": 150.0,
        "cpu": 90.0,
        "memory": 90.0
    },
    "pdf-generator-worker": {
        "latency": 500.0,
        "cpu": 85.0,
        "memory": 95.0
    },
    "default": {
        "latency": 250.0,
        "cpu": 90.0,
        "memory": 95.0
    }
}

table = dynamodb.Table(TABLE_NAME)

def lambda_handler(event, context):
    print("Auditor Lambda triggered with event:", json.dumps(event))
    
    if event.get('httpMethod') == 'GET':
        claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
        user_role = claims.get('custom:role')
        user_email = claims.get('email')
        
        if user_role != 'Admin' and user_email != 'vaibhavsp16@gmail.com':
            return response_api(403, {"error": "Access Denied: Only Admin users can view SLA reports"})
            
        query_params = event.get('queryStringParameters') or {}
        if query_params.get('type') == 'raw':
            try:
                response = table.scan(
                    FilterExpression="begins_with(PK, :sp) OR begins_with(PK, :dp)",
                    ExpressionAttributeValues={
                        ":sp": "SERVER#",
                        ":dp": "DEVICE#"
                    }
                )
                items = response.get('Items', [])
                items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                return response_api(200, items)
            except Exception as e:
                print(f"Error scanning raw logs: {str(e)}")
                return response_api(500, {"error": "Failed to fetch raw server logs"})

        try:
            response = table.query(
                KeyConditionExpression=Key('PK').eq('REPORT#DAILY'),
                ScanIndexForward=False 
            )
            items = response.get('Items', [])
            for item in items:
                devices_set = item.get('active_devices', set())
                item['total_active_devices'] = len(devices_set)
                
                anom_set = item.get('anomaly_devices', set())
                item['anomaly_devices_list'] = ", ".join(sorted(list(anom_set))) if anom_set else "None"
                
                item['gateway_spikes_count'] = int(item.get('gateway_spikes_count', 0))
                item['cpu_overloads_count'] = int(item.get('cpu_overloads_count', 0))
                item['memory_crashes_count'] = int(item.get('memory_crashes_count', 0))
                
                for k in ['active_devices', 'anomaly_devices', 'surge_devices', 'overvoltage_devices', 'undervoltage_devices']:
                    if k in item:
                        del item[k]
                    
            return response_api(200, items)
        except Exception as e:
            print(f"Error querying SLA reports: {str(e)}")
            return response_api(500, {"error": "Failed to fetch reports list"})

    try:
        response = table.scan()
        items = response.get('Items', [])
        
        incidents = []
        aggregates = set()
        
        for item in items:
            sk = str(item.get('SK'))
            if sk.startswith('LOG#') or sk.startswith('READING#'):
                device_id = item.get('device_id')
                aggregates.add(device_id)
                
                thresholds = DEVICE_THRESHOLDS.get(device_id, DEVICE_THRESHOLDS["default"])
                latency = float(item.get('latency') or 0)
                cpu = float(item.get('cpu_utilization') or 0)
                memory = float(item.get('memory_utilization') or 0)
                
                if latency > thresholds["latency"]:
                    incidents.append({
                        "device_id": device_id,
                        "metric": f"Latency Spike ({latency}ms)",
                        "timestamp": item.get('timestamp')
                    })
                elif cpu > thresholds["cpu"]:
                    incidents.append({
                        "device_id": device_id,
                        "metric": f"CPU Overload ({cpu}%)",
                        "timestamp": item.get('timestamp')
                    })
                elif memory > thresholds["memory"]:
                    incidents.append({
                        "device_id": device_id,
                        "metric": f"Memory Crash ({memory}%)",
                        "timestamp": item.get('timestamp')
                    })
                
        print(f"Daily Audit completed. Scan count: {len(items)}. Incidents detected: {len(incidents)}")
        if incidents:
            msg = f"WARNING: Daily Infrastructure Audit Report - Outages detected!\n\n"
            msg += f"The following servers exceeded safety SLA bounds today:\n"
            for inc in incidents:
                msg += f"- Server {inc['device_id']}: {inc['metric']} at {inc['timestamp']}\n"
            
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject="CRITICAL: Daily ServerWatch Incident Audit Summary",
                Message=msg
            )
            print("SNS audit alert email sent successfully.")
            
        report_id = datetime.utcnow().strftime("%Y-%m-%d")
        report_item = {
            'PK': "REPORT#DAILY",
            'SK': f"DATE#{report_id}",
            'report_date': report_id,
            'total_active_devices': len(aggregates),
            'timestamp': datetime.utcnow().isoformat(),
            'gateway_spikes_count': 0,
            'cpu_overloads_count': len(incidents),
            'memory_crashes_count': 0
        }
        table.put_item(Item=report_item)
        print(f"Daily Server SLA report saved under Key: REPORT#DAILY | DATE#{report_id}")
        
    except Exception as err:
        print(f"Error executing daily audit check: {str(err)}")
        raise err
        
    return {
        'statusCode': 200,
        'body': json.dumps('Audit finished successfully')
    }

def response_api(status_code, body_dict):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body_dict, cls=DecimalEncoder)
    }
