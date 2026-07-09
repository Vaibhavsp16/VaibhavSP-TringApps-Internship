# ServerWatch APM Telemetry & SLA Audit Portal

ServerWatch is a serverless Application Performance Monitoring (APM) and SLA (Service Level Agreement) compliance platform built on Amazon Web Services (AWS) using Terraform for Infrastructure as Code (IaC). It ingests real-time metrics, flags anomalies, sends notifications, registers daily audits, and provides interactive AI-driven log diagnostics using Google Gemini AI.

---

## Project Structure

```
Capstone Project/
├── frontend/
│   ├── index.html        # Single Page Web App (APM Dashboard)
│   └── config.js         # Auto-generated API coordinates (Terraform output)
├── lambda/
│   ├── ingestion.py      # Telemetry intake proxy handler (SQS producer)
│   ├── processor.py      # Event-driven anomaly evaluator (SQS consumer)
│   └── auditor.py        # Daily cron compliance reports and REST API engine
├── main.tf               # Primary Terraform configuration code
├── variables.tf          # Terraform variable declarations
├── outputs.tf            # Output values printed post-deploy
├── terraform.tfvars      # Local secret variables (sensitive/gitignored)
└── simulate_devices.py   # Local Python client to stream simulated telemetry
```

---

## Core Cloud Architecture

1. **Ingestion REST API**: API Gateway receives JSON metrics and forwards them to the **Ingestion Lambda**.
2. **Buffering Queue**: The Ingestion Lambda dumps payloads into **Amazon SQS**, protecting the backend database from sudden spikes.
3. **Telemetry Processing**: The **Processor Lambda** reads messages from SQS, tests metrics against server limits, writes logs to **DynamoDB**, and triggers emails via **Amazon SNS** if anomalies are caught.
4. **Scheduled SLA Audits**: **Amazon EventBridge Scheduler** runs the **Auditor Lambda** once a day to aggregate logs and write Daily SLA Summaries to DynamoDB.
5. **Admin Access Portal**: Front-end UI hosted on **Amazon S3** and cached at **Amazon CloudFront** edge sites, secured by **Amazon Cognito** user pool JWT authorizers.

---

## Setup & Deployment Guide

### 1. Prerequisites
Ensure you have the following CLI utilities installed:
* AWS CLI configured with active credentials (`aws configure`)
* Terraform CLI (v1.5+)
* Python 3.9+

### 2. Configure Local Secrets
Create a file named `terraform.tfvars` in the root folder and configure your sensitive keys:
```hcl
gemini_api_key = "YOUR_GOOGLE_GEMINI_API_KEY_HERE"
```

### 3. Deploy Resources using Terraform
Initialize and deploy the cloud stack:
```powershell
terraform init
terraform plan -out=tfplan
terraform apply "tfplan"
```

Once deployment completes, copy the printed `cloudfront_url` and `api_endpoint_url` from the terminal outputs.

---

## Telemetry Simulator Guide

To stream metrics to the dashboard, use the simulation agent:
1. Initialize the virtual environment (if not already done):
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install requests
   ```
2. Launch the script:
   ```powershell
   python simulate_devices.py
   ```
3. When prompted, input your API Gateway Endpoint URL (the `api_endpoint_url` output from Terraform).
4. The simulator will stream healthy logs and inject anomalies every 6th run to verify the alerting and graphing behaviors.

---

## Key Features Guide

### 📂 Live Dashboard Feed
* Displays user session tokens for JWT verification.
* Features a sandbox simulator to submit instant metrics.
* Displays a daily SLA audit table showing server counts, latency breaches, and system healthy flags in a scrollbox display.

### 📊 Health Analytics
* Displays 4 responsive performance charts (Gateway latency spikes, RAM/CPU crashes, warning distributions, and SLA ratios).
* Features dynamic timeframe selectors to filter analytics trends in real-time.

### 💬 AI DevOps Assistant
* Connects the local dashboard logs to the **Gemini 2.5 Flash** model.
* Provides executive summary reports stripped of markdown stars and formatted with round bullet points.
* Supports active chat queries to help troubleshoot specific incident days.
