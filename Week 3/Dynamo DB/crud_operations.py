import boto3
import uuid
from datetime import datetime

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('FeedbackAPI_Table')

def run_local_diagnostic():
    print("Initiating direct workstation-to-database connection diagnostic tests...")
    test_id = str(uuid.uuid4())
    
    try:
        table.put_item(
            Item={
                'feedback_id': test_id,
                'username': 'local_workstation_test',
                'feedback': 'Diagnostic write validation checking from local console environment.',
                'timestamp': datetime.utcnow().isoformat()
            }
        )
        print(f"SUCCESS: Data written to table. Row ID token: {test_id}")
        
        read_check = table.get_item(Key={'feedback_id': test_id})
        if 'Item' in read_check:
            print(f"SUCCESS: Read row verification complete. Data: {read_check['Item']['feedback']}")
            
    except Exception as network_error:
        print(f"DIAGNOSTIC CRITICAL FAIL: {str(network_error)}")

if __name__ == '__main__':
    run_local_diagnostic()