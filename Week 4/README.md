# Serverless Event-Driven Pipeline Architecture (Week 4)

This repository provisions an event-driven file processing architecture on AWS using Terraform. It uses Amazon S3 upload triggers, Amazon SQS decoupling queues, Dead Letter Queues (DLQ) for fault isolation, and AWS Lambda processing.

---

## Architecture
* **Amazon S3** receives raw document and image uploads.
* **S3 Event Notifications** automatically publish `ObjectCreated` events to the queue.
* **Amazon SQS** decouples S3 from the processing layer, holding logs in-flight.
* **AWS Lambda** pulls events from SQS in batches to execute background calculations.
* **SQS Dead Letter Queue (DLQ)** intercepts corrupt payloads, isolating failures.

---

## Security Features
* **Private S3 Storage**: All public bucket access blocks are enforced.
* **IAM Least Privilege**: Custom policies authorize SQS to consume S3 notifications and Lambda to poll SQS.

---

## Repository Structure
```
Week 4/
├── lambda/         # Python Lambda processor functions
├── main.tf         # Terraform IaC configuration
├── outputs.tf      # Infrastructure deployment outputs
├── variables.tf    # Infrastructure input variables
└── README.md       # Week 4 Documentation Guide
```

---

## Prerequisites

### Tools
* Terraform >= 1.5
* AWS CLI configured
* Python 3.9+

### AWS Permissions
Ensure the AWS identity has permissions for:
* Amazon S3 (Bucket triggers, lifecycle rules)
* Amazon SQS (Queues, redrive policies)
* AWS Lambda (Zip packaging, execution roles)
* IAM Policies

---

## Configure & Deploy Terraform

### 1. Initialize Terraform
Navigate to the Week 4 directory and initialize providers:
```bash
terraform init
```

### 2. Preview Deployment Plan
Review the resources (S3, SQS, Lambda) to be created:
```bash
terraform plan
```

### 3. Deploy Stack
Provision the active event-driven architecture on AWS:
```bash
terraform apply -auto-approve
```

---

## Testing

### 1. Verify S3 Object Upload
Upload a test file to the target S3 bucket:
```bash
aws s3 cp image.jpg s3://<your-bucket-name>/image.jpg
```

### 2. Verify SQS Message Queuing
Confirm the upload event was sent to SQS:
```bash
aws sqs receive-message --queue-url <your-sqs-queue-url>
```
**Expected Output:**
A JSON payload containing details of the S3 upload (`image.jpg`, timestamp, size).

### 3. Verify Lambda Trigger Execution
Check the Lambda CloudWatch logs to verify it parsed the SQS message:
```bash
aws logs tail /aws/lambda/<your-lambda-function-name>
```
**Expected Output:**
```
[INFO] Processing S3 event: image.jpg from bucket <your-bucket-name>
```

### 4. Verify Dead Letter Queue (DLQ) Isolation
Send a malformed payload directly to SQS and fail it 3 times to test the DLQ routing:
```bash
aws sqs send-message --queue-url <your-sqs-queue-url> --message-body '{"corrupt": true}'
```
Wait for Lambda to retry and fail. Query the DLQ:
```bash
aws sqs receive-message --queue-url <your-dlq-url>
```
**Expected Output:**
The corrupt message is present, proving successful isolation.

---

## Cleanup
Destroy all provisioned assets:
```bash
terraform destroy -auto-approve
```

---

## Troubleshooting

### S3 Notification fails to deploy
* **Verify**: The SQS Queue policy has a statement permitting the S3 bucket ARN to execute `sqs:SendMessage`. Without this permission, S3 cannot push notifications.

### Lambda is not triggered by SQS
* **Verify**: The SQS trigger event source mapping is active (`Enabled = true`) on the Lambda function settings.
* **Verify**: The Lambda role has permissions to execute `sqs:ReceiveMessage` and `sqs:DeleteMessage`.
