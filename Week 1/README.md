# AWS Cloud and Core Storage Infrastructure (Week 1)

This project provisions and configures foundational AWS core infrastructure, including secure Amazon S3 storage buckets, least-privilege IAM policies, and an Amazon EC2 Linux virtual machine hosting a live Apache Web Server.

---

## Architecture
* **Amazon S3** hosts private document repositories and stores asset backups.
* **Amazon EC2** hosts the Apache web application in a public subnet.
* **IAM Roles** provide EC2 instances secure access to S3 without embedding API credentials.
* **Security Groups** enforce stateful firewalls controlling inbound HTTP (80) and SSH (22) traffic.

---

## Security Features
* **S3 Block Public Access** is enabled on all buckets to prevent data leakage.
* **IAM Roles & Instance Profiles** grant temporary security tokens to EC2.
* **SSH Key Pair Encryption** prevents password brute-forcing on the EC2 host.

---

## Repository Structure
```
Week 1/
├── EC2/            # EC2 provisioning scripts and user-data logs
├── IAM/            # Custom trust policies and role definitions
├── S3/             # Bucket policy parameters and configuration configs
└── README.md       # Week 1 Documentation Guide
```

---

## Prerequisites

### Tools
* AWS CLI configured (`aws configure`)
* SSH Client (e.g. OpenSSH, PuTTY)
* Git

### AWS Permissions
Ensure the AWS identity has permissions for:
* Amazon EC2 (Instance creation, Security Groups, Key Pairs)
* Amazon S3 (Bucket creation, Bucket Policies)
* AWS IAM (Role creation, Instance Profiles)

---

## Infrastructure Deployment

### 1. Configure S3 Storage
Create the bucket and apply blocking rules:
```bash
aws s3api create-bucket --bucket smartwatt-core-storage --region us-east-1
aws s3api put-public-access-block \
  --bucket smartwatt-core-storage \
  --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

### 2. Configure IAM Access
Create the instance profile and bind the S3 read policy to the EC2 role:
```bash
aws iam create-role --role-name EC2S3ReadOnlyRole --assume-role-policy-document file://IAM/trust-policy.json
aws iam attach-role-policy --role-name EC2S3ReadOnlyRole --policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess
aws iam create-instance-profile --instance-profile-name EC2S3InstanceProfile
aws iam add-role-to-instance-profile --instance-profile-name EC2S3InstanceProfile --role-name EC2S3ReadOnlyRole
```

### 3. Provision the EC2 Host
Launch the host with custom Apache user-data:
```bash
aws ec2 run-instances \
  --image-id ami-0c7217cdde317cfec \
  --count 1 \
  --instance-type t2.micro \
  --key-name my-ssh-key \
  --security-group-ids sg-01234abc \
  --iam-instance-profile Name=EC2S3InstanceProfile \
  --user-data file://EC2/install_apache.sh
```

---

## Testing

### 1. Verify S3 Access Block
Attempt to access an object directly without credentials:
```bash
curl https://smartwatt-core-storage.s3.amazonaws.com/backup.txt
```
**Expected Output:**
```xml
<Error><Code>AccessDenied</Code>...</Error>
```

### 2. Verify EC2 SSH Connection
Connect using your private PEM key:
```bash
ssh -i "my-ssh-key.pem" ec2-user@<ec2-public-ip>
```
**Expected Output:**
```
[ec2-user@ip-172-31-0-1 ~]$
```

### 3. Verify IAM Instance profile S3 Access
From inside the EC2 session, list S3 buckets using the instance profile metadata credentials:
```bash
aws s3 ls s3://smartwatt-core-storage
```
**Expected Output:**
List of files inside the bucket.

### 4. Verify Apache Web Server
Test the HTTP port via a web browser or curl:
```bash
curl -I http://<ec2-public-ip>
```
**Expected Output:**
```
HTTP/1.1 200 OK
Server: Apache/2.4.x
```

---

## Cleanup
Tear down resources to prevent billing charges:
```bash
aws ec2 terminate-instances --instance-ids <instance-id>
aws s3 rb s3://smartwatt-core-storage --force
aws iam remove-role-from-instance-profile --instance-profile-name EC2S3InstanceProfile --role-name EC2S3ReadOnlyRole
aws iam delete-instance-profile --instance-profile-name EC2S3InstanceProfile
aws iam delete-role --role-name EC2S3ReadOnlyRole
```

---

## Troubleshooting

### Connection Timeout on SSH/HTTP
* **Verify**: The Security Group rules allow inbound TCP port 22 and 80 from your IP address.
* **Verify**: The EC2 instance is associated with a public IP.

### IAM Profile does not authorize S3
* **Verify**: At least 2 minutes have passed since instance profile association (IAM has propagation latency).
* **Verify**: The IAM instance profile is correctly bound to the EC2 instance in the AWS console.
