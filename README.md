# AWS Cloud & Serverless Engineering Internship Portfolio

Welcome to my Cloud Engineering internship repository. This workspace catalogs my progressive learning, architectural implementations, and automated infrastructure deployments on Amazon Web Services (AWS) over 6 weeks.

---

## 📅 Weekly Curriculum Overview

### [📂 Week 1: Core AWS Storage & Virtual Infrastructure](./Week%201)
* **Objective**: Establish foundational cloud compute, IAM roles, and storage services.
* **Tech Stack**: Amazon S3, Amazon EC2, Apache Linux Web Server, AWS IAM.
* **Key Achievements**: Configured private S3 repositories, provisioned Linux servers via CLI with user-data automation, and decoupled permission mappings using EC2 IAM Instance Profiles.

### [📂 Week 2: Serverless Computes & REST APIs](./Week%202)
* **Objective**: Shift from virtual hosts to serverless compute blocks.
* **Tech Stack**: AWS Lambda, Amazon API Gateway, Python.
* **Key Achievements**: Implemented a feedback intake REST API. Set up API Gateway endpoint routes and custom Lambda handlers with CORS headers.

### [📂 Week 3: Databases & Persistent NoSQL Storage](./Week%203)
* **Objective**: Integrate low-latency persistent databases into the serverless compute layer.
* **Tech Stack**: Amazon DynamoDB, AWS Lambda, boto3 (Python AWS SDK).
* **Key Achievements**: Provisioned DynamoDB tables using On-Demand capacity. Configured secure write/read operations from Lambda handlers.

### [📂 Week 4: Event-Driven Architectures & Message Queues](./Week%204)
* **Objective**: Decouple architectures to ensure system scalability and prevent data loss.
* **Tech Stack**: Amazon S3, Amazon SQS, Dead Letter Queue (DLQ), AWS Lambda, Terraform (IaC).
* **Key Achievements**: Programmed automated S3 notification triggers to push uploads to SQS. Configured SQS batch processing and implemented a SQS DLQ for automatic isolation of corrupt logs.

### [📂 Week 5: Serverless IaC & CI/CD Pipelines](./Week%205)
* **Objective**: Automate infrastructure deployments and environment configurations.
* **Tech Stack**: AWS SAM (Serverless Application Model), Docker, GitHub Actions CI/CD.
* **Key Achievements**: Defined serverless stacks in SAM YAML. Simulated API environments locally using Docker containers. Configured GitHub Actions to validate and deploy code automatically on git push.

### [📂 Week 6: ServerWatch APM & AI Diagnostics (Capstone Project)](./Capstone%20Project)
* **Objective**: Build a production-grade Application Performance Monitoring (APM) and SLA Audit Portal.
* **Tech Stack**: API Gateway, Amazon SQS, AWS Lambda, DynamoDB Single-Table Design, Amazon SNS, Google Gemini 2.5 Flash API, Terraform.
* **Key Achievements**: Engineered high-throughput metrics ingestion queues. Designed a Single-Table DynamoDB schema for log-reporting segregation. Integrated Google Gemini AI to analyze raw server logs and compile clean plain-text diagnostic summaries.
