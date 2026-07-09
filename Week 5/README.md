# Serverless Infrastructure as Code and CI/CD (Week 5)

This repository provisions a serverless application on AWS using the AWS Serverless Application Model (SAM) for IaC, and defines a GitHub Actions CI/CD workflow for automated deployments.

---

## Architecture
* **AWS SAM YAML template** defines serverless resources (Lambdas, API paths, and simple tables).
* **API Gateway** endpoints trigger the Lambda handler function.
* **GitHub Actions** workflows automate building, testing, and deploying the SAM stacks.

---

## Security Features
* **GitHub Encrypted Secrets** secure the AWS deployment credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`).
* **CloudFormation IAM execution roles** isolate deployment scopes.

---

## Repository Structure
```
Week 5/
├── hello.py            # Lambda handler python function
├── template.yaml       # SAM template declaring resources
├── samconfig.toml      # Environment and deployment configurations
└── README.md           # Week 5 Documentation Guide
```

---

## Prerequisites

### Tools
* AWS SAM CLI
* AWS CLI configured
* Docker (required for local API simulation)
* Python 3.9+

---

## Configure & Local Test

### 1. Build the Application
Compile the functions and packaging dependencies:
```bash
sam build
```

### 2. Validate SAM template
Ensure the YAML syntax is valid and CloudFormation compatible:
```bash
sam validate
```

### 3. Simulate API locally
Run the API gateway locally inside a Docker container:
```bash
sam local start-api
```
Open:
`http://1277.0.0.1:3000/hello`

### 4. Deploy Infrastructure
Deploy the stack to AWS:
```bash
sam deploy --guided
```
This updates `samconfig.toml` with default parameters for future builds.

---

## Testing

### 1. Verify Local API Call
Query the local Docker endpoint:
```bash
curl http://127.0.0.1:3000/hello
```
**Expected Response:**
```json
{"message": "hello world"}
```

### 2. Verify Live Cloud API Response
Get the deployed CloudFormation output URL:
```bash
curl https://<api-id>.execute-api.us-east-1.amazonaws.com/Prod/hello
```
**Expected Response:**
```json
{"message": "hello world"}
```

---

## GitHub Actions Deployment
Add the AWS credentials secrets to your GitHub repository:
* `AWS_ACCESS_KEY_ID`
* `AWS_SECRET_ACCESS_KEY`

Whenever code is pushed to the `main` branch, the workflow will automatically:
1. Run lint checks.
2. Build the SAM template.
3. Deploy to the cloud stack.

---

## Cleanup
Remove the CloudFormation stack:
```bash
sam delete --stack-name <your-stack-name>
```

---

## Troubleshooting

### Docker Daemon Not Running
* **Symptom**: `sam local start-api` fails indicating Docker is missing.
* **Fix**: Start your Docker Desktop engine. AWS SAM relies on Docker to build containerized runtime simulations.

### Deployment Rollbacks
* **Symptom**: `sam deploy` fails and rolls back resource creations.
* **Fix**: Run `aws cloudformation describe-stack-events --stack-name <your-stack-name>` to identify the specific resource configuration that failed.
