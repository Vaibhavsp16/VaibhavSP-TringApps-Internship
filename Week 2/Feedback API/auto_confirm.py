def lambda_handler(event, context):
    event['response']['autoConfirmUser'] = True
    
    if 'email' in event['request']['userAttributes']:
        event['response']['autoVerifyEmail'] = True
    else:
        event['response']['autoVerifyEmail'] = False
        
    return event