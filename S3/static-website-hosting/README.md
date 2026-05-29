# Static Website Hosting on AWS S3, CloudFront, Terraform, and GitHub Actions

This project deploys a static portfolio website to AWS using Terraform and GitHub Actions.

The website files live in:

```text
S3/static-website-hosting/site/
```

The infrastructure creates:

- A private S3 origin bucket for the website files.
- A separate S3 logs bucket.
- CloudFront distribution for public HTTPS delivery.
- CloudFront Origin Access Control so users cannot directly read the private S3 bucket.
- S3 bucket policy allowing only CloudFront to read the website files.
- CloudFront access logging.
- S3 server access logging.
- AWS WAF rate limiting for basic edge protection.
- Remote Terraform state stored in a dedicated S3 backend bucket.
- GitHub Actions deployment pipeline.

## Architecture

```text
User Browser
    |
    v
CloudFront Distribution
    |
    v
Private S3 Origin Bucket

Logs:
CloudFront logs -> S3 logs bucket/cloudfront-edge-logs/
S3 access logs  -> S3 logs bucket/s3-access-logs/

Terraform state:
S3 backend bucket/static-website-hosting/terraform.tfstate
```

## Repository Layout

```text
.
|-- .github/
|   `-- workflows/
|       `-- deploy.yml
`-- S3/
    `-- static-website-hosting/
        |-- main.tf
        |-- outputs.tf
        |-- variables.tf
        |-- README.md
        |-- .terraform.lock.hcl
        `-- site/
            |-- index.html
            `-- profile.jpg
```

## Prerequisites

Install these locally:

- Git
- Terraform
- AWS CLI
- A GitHub account
- An AWS account

Verify local tools:

```bash
git --version
terraform version
aws --version
```

Configure AWS CLI locally:

```bash
aws configure
```

Enter:

```text
AWS Access Key ID
AWS Secret Access Key
Default region: us-east-1
Default output format: json
```

Use `us-east-1` for this project because CloudFront WAF resources must be created in `us-east-1`.

## AWS IAM Setup

Create an IAM user or role for deployment. For a training or internship project, the simplest option is an IAM user with programmatic access.

The deploy identity needs permissions for:

- S3
- CloudFront
- WAFv2
- IAM policy document evaluation through Terraform provider APIs
- Terraform state bucket access

For production, use least privilege. For learning, `AdministratorAccess` is commonly used temporarily, but remove broad access when the project is complete.

Required GitHub secrets:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
```

## Step 1: Clone or Fork the Repository

Clone your repository:

```bash
git clone <YOUR_REPOSITORY_URL>
cd <YOUR_REPOSITORY_FOLDER>
```

Project commands in this guide assume the Terraform folder is:

```text
S3/static-website-hosting
```

## Step 2: Create the Terraform Remote State Bucket

Terraform needs a remote backend so GitHub Actions remembers previously created AWS resources.

Without remote state, every GitHub Actions run may create new S3 buckets and new CloudFront distributions.

Choose a globally unique state bucket name. A good pattern is:

```text
<your-name>-static-website-tfstate-<aws-account-id>
```

Get your AWS account ID:

```bash
aws sts get-caller-identity --query Account --output text
```

Create the backend bucket in `us-east-1`:

```bash
aws s3api create-bucket \
  --bucket <YOUR_TERRAFORM_STATE_BUCKET> \
  --region us-east-1
```

Enable versioning:

```bash
aws s3api put-bucket-versioning \
  --bucket <YOUR_TERRAFORM_STATE_BUCKET> \
  --versioning-configuration Status=Enabled
```

Enable encryption:

```bash
aws s3api put-bucket-encryption \
  --bucket <YOUR_TERRAFORM_STATE_BUCKET> \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

Block public access:

```bash
aws s3api put-public-access-block \
  --bucket <YOUR_TERRAFORM_STATE_BUCKET> \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

Important: never delete this Terraform state bucket unless you intentionally want Terraform to forget the infrastructure.

## Step 3: Configure Terraform Backend

Open:

```text
S3/static-website-hosting/main.tf
```

Update the backend block:

```hcl
terraform {
  backend "s3" {
    bucket  = "<YOUR_TERRAFORM_STATE_BUCKET>"
    key     = "static-website-hosting/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}
```

In this repository, the current backend bucket is:

```text
vaibhav-static-website-tfstate-285977275740
```

If another person uses this project, they must replace that value with their own backend bucket name.

## Step 4: Configure Project Variables

Open:

```text
S3/static-website-hosting/variables.tf
```

Current values:

```hcl
variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "bucket_name" {
  type    = string
  default = "vaibhav-static-website-bucket"
}
```

Change `bucket_name` for your own project:

```hcl
default = "your-name-static-website-bucket"
```

Terraform appends a random suffix, so the actual buckets become:

```text
your-name-static-website-bucket-origin-xxxxxxxx
your-name-static-website-bucket-logs-xxxxxxxx
```

The random suffix is stored in Terraform state. After remote state is working, it remains stable across future deployments.

## Step 5: Add Website Files

Place your static website files inside:

```text
S3/static-website-hosting/site/
```

Minimum required file:

```text
index.html
```

Optional files:

```text
profile.jpg
style.css
script.js
assets/
```

The GitHub Actions workflow uploads everything inside `site/` to the active S3 origin bucket:

```bash
aws s3 sync ./site s3://${{ env.BUCKET_NAME }} --delete
```

The `--delete` flag removes files from S3 that no longer exist locally.

## Step 6: Initialize and Validate Terraform Locally

From the repository root:

```bash
cd S3/static-website-hosting
terraform init
terraform fmt
terraform validate
```

Expected result:

```text
Terraform has been successfully initialized.
Success! The configuration is valid.
```

Optional dry run:

```bash
terraform plan
```

## Step 7: GitHub Repository Setup

Push the project to GitHub.

The workflow file must be at:

```text
.github/workflows/deploy.yml
```

GitHub Actions only detects workflow files under the root `.github/workflows/` directory.

## Step 8: Add GitHub Secrets

In GitHub:

1. Open your repository.
2. Go to **Settings**.
3. Go to **Secrets and variables**.
4. Open **Actions**.
5. Click **New repository secret**.
6. Add:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
```

These are used by:

```yaml
- name: Authenticate Cloud Session
  uses: aws-actions/configure-aws-credentials@v4
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    aws-region: us-east-1
```

## Step 9: GitHub Actions Deployment Flow

The workflow runs when code is pushed to `main`:

```yaml
on:
    push:
        branches:
            - main
```

The pipeline does this:

1. Checks out the repository.
2. Authenticates to AWS.
3. Installs Terraform.
4. Runs `terraform init`.
5. Runs `terraform apply -auto-approve`.
6. Reads Terraform outputs:

```bash
terraform output -raw origin_bucket_name
terraform output -raw cloudfront_distribution_id
```

7. Uploads `site/` files to the S3 origin bucket.
8. Invalidates CloudFront cache using:

```bash
aws cloudfront create-invalidation --distribution-id <DIST_ID> --paths "/*"
```

## Step 10: Push and Deploy

From the repository root:

```bash
git status
git add .
git commit -m "Deploy static website hosting project"
git push origin main
```

Then in GitHub:

1. Open the repository.
2. Click **Actions**.
3. Open the latest workflow run.
4. Wait for all steps to complete successfully.

## Step 11: Get the CloudFront Website URL

After deployment, get the website URL locally:

```bash
cd S3/static-website-hosting
terraform output cloudfront_url
```

Example output:

```text
"https://dua88g8j3o5ks.cloudfront.net"
```

Open the URL in your browser.

You can also find it in AWS:

1. Go to **CloudFront**.
2. Open **Distributions**.
3. Select the active distribution.
4. Copy the **Distribution domain name**.

## Step 12: Confirm Active Resources

Use Terraform outputs:

```bash
terraform output -raw origin_bucket_name
terraform output -raw cloudfront_distribution_id
terraform output -raw cloudfront_url
```

Example:

```text
Origin bucket: vaibhav-static-website-bucket-origin-5ff0f9da
Distribution: E1DIT6DX9RHUG9
Website: https://dua88g8j3o5ks.cloudfront.net
```

Use Terraform state to confirm the logs bucket:

```bash
terraform state show aws_s3_bucket.logs
```

Look for:

```text
bucket = "<logs-bucket-name>"
```

## Caching Behavior

CloudFront caching is configured in `main.tf`:

```hcl
min_ttl     = 0
default_ttl = 3600
max_ttl     = 86400
```

Meaning:

```text
default cache time: 1 hour
maximum cache time: 1 day
```

Every GitHub Actions deployment also clears CloudFront cache:

```bash
aws cloudfront create-invalidation --distribution-id ${{ env.DIST_ID }} --paths "/*"
```

So after every deployment, users should receive the latest files once the invalidation completes.

## Logging

This project has two types of logging.

### CloudFront Access Logs

Configured in `main.tf`:

```hcl
logging_config {
  bucket = aws_s3_bucket.logs.bucket_domain_name
  prefix = "cloudfront-edge-logs/"
}
```

View logs in S3:

```text
<logs-bucket>/cloudfront-edge-logs/
```

Example:

```text
s3://vaibhav-static-website-bucket-logs-5ff0f9da/cloudfront-edge-logs/
```

CloudFront logs are delivered as `.gz` files and may take several minutes to appear.

### S3 Server Access Logs

Configured in `main.tf`:

```hcl
resource "aws_s3_bucket_logging" "origin_logging" {
  bucket        = aws_s3_bucket.origin.id
  target_bucket = aws_s3_bucket.logs.id
  target_prefix = "s3-access-logs/"
}
```

View logs in S3:

```text
<logs-bucket>/s3-access-logs/
```

## Security Notes

The origin S3 bucket is private.

Public access is blocked:

```hcl
block_public_acls       = true
block_public_policy     = true
ignore_public_acls      = true
restrict_public_buckets = true
```

CloudFront gets access through Origin Access Control:

```hcl
resource "aws_cloudfront_origin_access_control" "oac" {
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}
```

The bucket policy allows CloudFront only:

```hcl
principals {
  type        = "Service"
  identifiers = ["cloudfront.amazonaws.com"]
}
```

## WAF Protection

This project creates a WAF Web ACL for CloudFront:

```hcl
resource "aws_wafv2_web_acl" "waf" {
  scope = "CLOUDFRONT"
}
```

The rule blocks an IP if it crosses the configured request rate:

```hcl
rate_based_statement {
  limit              = 300
  aggregate_key_type = "IP"
}
```

## Common Problems and Fixes

### `terraform: command not found`

Cause:

GitHub Actions runner does not have Terraform installed.

Fix:

The workflow must include:

```yaml
- name: Install Terraform CLI
  uses: hashicorp/setup-terraform@v3
  with:
    terraform_wrapper: false
```

### Terraform creates new buckets on every run

Cause:

Terraform state is not persisted.

Fix:

Use the remote S3 backend:

```hcl
terraform {
  backend "s3" {
    bucket  = "<YOUR_TERRAFORM_STATE_BUCKET>"
    key     = "static-website-hosting/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}
```

### `Reference to undeclared resource`

Cause:

A Terraform resource or data source name does not match.

Example fix:

```hcl
policy = data.aws_iam_policy_document.oac_policy_doc.json
```

The referenced name must match:

```hcl
data "aws_iam_policy_document" "oac_policy_doc" {}
```

### `NoSuchBucket` during S3 sync

Cause:

The workflow is reading the wrong Terraform output.

Fix:

The workflow should use:

```bash
terraform output -raw origin_bucket_name
```

### Website still shows old content

Cause:

CloudFront cache has not completed invalidation yet.

Fix:

Wait a few minutes and refresh. You can also check invalidations in:

```text
CloudFront -> Distribution -> Invalidations
```

### Direct S3 website endpoint does not work

This is expected.

The S3 bucket is private. Use the CloudFront URL instead.

## Cleanup Old Duplicate Resources

If Terraform was run before remote state was configured, AWS may contain duplicate S3 buckets and CloudFront distributions.

Keep:

- The active origin bucket from:

```bash
terraform output -raw origin_bucket_name
```

- The active CloudFront distribution from:

```bash
terraform output -raw cloudfront_distribution_id
```

- The logs bucket from:

```bash
terraform state show aws_s3_bucket.logs
```

- The Terraform state bucket configured in the backend block.

Delete only old duplicate S3 buckets and old duplicate CloudFront distributions that are not in Terraform state.

CloudFront deletion process:

1. Open CloudFront.
2. Select the old distribution.
3. Disable it.
4. Wait until status becomes `Deployed`.
5. Delete it.

S3 bucket deletion process:

1. Empty the old bucket.
2. Delete the old bucket.

Do not delete the Terraform state bucket.

## Destroying the Project

If you intentionally want to remove the website infrastructure:

```bash
cd S3/static-website-hosting
terraform destroy
```

This removes resources managed by Terraform.

After destroy, manually decide whether to keep or delete the Terraform state bucket. For normal project history, keep it. For permanent cleanup, delete it only after you are sure the project is no longer needed.

## Maintenance Checklist

For future updates:

1. Edit files inside `S3/static-website-hosting/site/`.
2. Commit and push to `main`.
3. Watch GitHub Actions.
4. Open the CloudFront URL.
5. Check CloudFront invalidation if old content appears.
6. Check S3 logs bucket if traffic logs are needed.

## Current Project Values

These values are specific to the current deployment:

```text
Terraform state bucket:
vaibhav-static-website-tfstate-285977275740

Active origin bucket:
vaibhav-static-website-bucket-origin-5ff0f9da

Active logs bucket:
vaibhav-static-website-bucket-logs-5ff0f9da

Active CloudFront distribution:
E1DIT6DX9RHUG9
```

If another person forks or reuses this project, they should replace the backend bucket and `bucket_name` variable with their own values.
