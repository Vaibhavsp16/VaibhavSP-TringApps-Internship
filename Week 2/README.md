# Serverless API and Compute Foundations (Week 2)

This repository provisions a Serverless Feedback Collection API on AWS, utilizing Amazon API Gateway for routing and AWS Lambda for serverless python backend execution.

---

## Architecture
* **Amazon API Gateway** exposes secure REST endpoints and manages API environments.
* **AWS Lambda** executes the feedback processing backend code on-demand, parsing incoming JSON and returning formatted responses.

---

## Security Features
* **CORS (Cross-Origin Resource Sharing)** rules restrict API access to valid origins.
* **Gateway Payload Validations** reject malformed requests before they invoke compute resources, minimizing costs.

---

## Repository Structure
```
Week 2/
├── Feedback API/   # OpenAPI configuration exports and stage maps
├── Lambda/         # Python Lambda handler functions
└── README.md       # Week 2 Documentation Guide
```

---

## Prerequisites

### Tools
* AWS CLI configured (`aws configure`)
* Python 3.9+ (for packaging)
* Postman (or curl) for endpoint testing

### AWS Permissions
Ensure the AWS identity has permissions for:
* AWS Lambda (Function creation, packaging uploads)
* Amazon API Gateway (REST API creation, deployments, stages)
* IAM (Lambda basic execution role permissions)

---

## Infrastructure Deployment

### 1. Create the Lambda Execution Role
Create a basic execution role so Lambda can write log outputs to CloudWatch:
```bash
aws iam create-role --role-name LambdaBasicRole --assume-role-policy-document file://Lambda/trust-policy.json
aws iam attach-role-policy --role-name LambdaBasicRole --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

### 2. Package and Deploy Lambda
Zip your python code and deploy the function:
```bash
compress-archive -Path Lambda/feedback_handler.py -DestinationPath Lambda/feedback_handler.zip
aws lambda create-function \
  --function-name process-feedback-dev \
  --runtime python3.9 \
  --handler feedback_handler.lambda_handler \
  --role arn:aws:iam::123456789012:role/LambdaBasicRole \
  --zip-file fileb://Lambda/feedback_handler.zip
```

### 3. Provision API Gateway REST API
Create the HTTP REST API resource and bind it as a trigger to the Lambda function:
```bash
aws apigateway create-rest-api --name feedback-api-dev --region us-east-1
# Configure resources and POST method...
aws apigateway create-deployment --rest-api-id <api-id> --stage-name dev
```

---

## Testing

### 1. Verify Direct Lambda Function Invocation
Execute the Lambda directly with mock JSON payloads:
```bash
aws lambda invoke \
  --function-name process-feedback-dev \
  --payload '{"name": "Alice", "feedback": "Great service!"}' \
  response.json
```
**Expected Output:**
`response.json` contains:
```json
{"statusCode": 200, "body": "{\"message\": \"Feedback processed successfully\"}"}
```

### 2. Verify API Gateway POST Route
Post a simulated feedback event using curl:
```bash
curl -X POST https://<api-id>.execute-api.us-east-1.amazonaws.com/dev/feedback \
  -H "Content-Type: application/json" \
  -d '{"name": "Bob", "feedback": "Nice interface"}'
```
**Expected Output:**
```json
{"message": "Feedback processed successfully"}
```

### 3. Verify CORS Header Responses
Verify that CORS headers are returned to options checks:
```bash
curl -I -X OPTIONS https://<api-id>.execute-api.us-east-1.amazonaws.com/dev/feedback
```
**Expected Output:**
```
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: POST,OPTIONS
```

---

## Cleanup
Remove resources to clean your environment:
```bash
aws apigateway delete-rest-api --rest-api-id <api-id>
aws lambda delete-function --function-name process-feedback-dev
aws iam detach-role-policy --role-name LambdaBasicRole --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name LambdaBasicRole
```

---

## Troubleshooting

### HTTP 500 Internal Server Error
* **Verify**: The Lambda function execution permissions allow API Gateway triggers (`aws lambda add-permission`).
* **Verify**: Check CloudWatch Log streams for Python runtime exceptions or syntax errors inside your Lambda handler.

### HTTP 403 Forbidden
* **Verify**: The API endpoint path is correct (remember that paths are case-sensitive and stage-dependent, e.g., `/dev/feedback`).
