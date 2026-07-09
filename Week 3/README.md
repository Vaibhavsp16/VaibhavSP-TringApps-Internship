# Serverless Database and Persistent Storage (Week 3)

This project integrates persistent NoSQL storage into the serverless backend, provisioning an Amazon DynamoDB table and implementing Python database connections using boto3.

---

## Architecture
* **Amazon DynamoDB** serves as the persistent NoSQL data layer, storing structured documents (such as telemetry or feedback records) with single-digit millisecond latency.
* **AWS Lambda** handles write/read requests, executing DB connectors to interact with the database tables.

---

## Security Features
* **Least-Privilege IAM Policies** grant the Lambda function only the necessary database permissions (`PutItem`, `GetItem`, `UpdateItem`), blocking all other actions.
* **Server-Side Encryption** protects DB storage at rest using AWS KMS keys.

---

## Repository Structure
```
Week 3/
├── Dynamo DB/      # Database schemas, scripts, and Python connection code
└── README.md       # Week 3 Documentation Guide
```

---

## Prerequisites

### Tools
* AWS CLI configured (`aws configure`)
* Python 3.9+

### AWS Permissions
Ensure the AWS identity has permissions for:
* Amazon DynamoDB (Table creation, updates, indexing)
* AWS IAM (Policy creation, roles mapping)

---

## Infrastructure Deployment

### 1. Provision the DynamoDB Table
Create the table using On-Demand billing to optimize cost:
```bash
aws dynamodb create-table \
  --table-name smartwatt-telemetry-dev \
  --attribute-definitions \
      AttributeName=PK,AttributeType=S \
      AttributeName=SK,AttributeType=S \
  --key-schema \
      AttributeName=PK,KeyType=HASH \
      AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### 2. Configure Lambda IAM Privileges
Create a custom policy allowing the Lambda to read and write to the specific table, and attach it to the Lambda role:
```bash
aws iam create-policy \
  --policy-name DynamoDBReadWritePolicy \
  --policy-document file://DynamoDB/policy.json
aws iam attach-role-policy \
  --role-name LambdaBasicRole \
  --policy-arn arn:aws:iam::123456789012:policy/DynamoDBReadWritePolicy
```

### 3. Deploy Python Code
Upload the updated python script executing boto3 writes:
```bash
compress-archive -Path Dynamo\ DB/db_handler.py -DestinationPath Dynamo\ DB/db_handler.zip
aws lambda update-function-code \
  --function-name process-feedback-dev \
  --zip-file fileb://Dynamo\ DB/db_handler.zip
```

---

## Testing

### 1. Verify Database Write (PutItem)
Simulate a write request by invoking the Lambda:
```bash
aws lambda invoke \
  --function-name process-feedback-dev \
  --payload '{"action": "create", "id": "user123", "data": "Test info"}' \
  response.json
```
**Expected Output:**
The DB record is written. Verify via CLI scan:
```bash
aws dynamodb scan --table-name smartwatt-telemetry-dev
```
**Expected Response:**
```json
{
    "Items": [
        {
            "PK": {"S": "USER#user123"},
            "SK": {"S": "METRIC#latest"},
            "data": {"S": "Test info"}
        }
    ],
    "Count": 1
}
```

### 2. Verify Database Read (GetItem)
Query the database directly using the partition key:
```bash
aws dynamodb get-item \
  --table-name smartwatt-telemetry-dev \
  --key '{"PK": {"S": "USER#user123"}, "SK": {"S": "METRIC#latest"}}'
```
**Expected Output:**
The exact item attributes return in JSON format.

---

## Cleanup
Remove the table and policies:
```bash
aws dynamodb delete-table --table-name smartwatt-telemetry-dev
aws iam detach-role-policy --role-name LambdaBasicRole --policy-arn arn:aws:iam::123456789012:policy/DynamoDBReadWritePolicy
aws iam delete-policy --policy-arn arn:aws:iam::123456789012:policy/DynamoDBReadWritePolicy
```

---

## Troubleshooting

### AccessDeniedException on DB Queries
* **Verify**: The IAM Policy ARN is correctly attached to the execution role of the Lambda.
* **Verify**: The Resource ARN listed in your IAM Policy matches the exact target table name (`smartwatt-telemetry-dev`).

### ResourceNotFoundException
* **Verify**: The table has completed provisioning and its status is `ACTIVE`.
* **Verify**: You are querying the same AWS region where the table was created (e.g. `us-east-1`).
