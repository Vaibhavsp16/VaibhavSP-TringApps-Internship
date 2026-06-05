import json

def lambda_handler(event, context):
    print("Received event: " + json.dumps(event))
    
    name = event.get('first_name', 'Vaibhav')
    
    return {
        'statusCode': 200,
        'body': json.dumps(f'Hello from Lambda, {name}!')
    }