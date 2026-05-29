# Static Website Hosting on AWS S3, CloudFront, Terraform, and GitHub Actions

This project deploys a static portfolio website to AWS with Terraform and GitHub Actions.

Website source files:

```text
S3/static-website-hosting/site/
```

The infrastructure creates:

- A private S3 origin bucket for website files.
- A separate S3 logs bucket.
- CloudFront distribution for HTTPS website delivery.
- CloudFront Origin Access Control so the S3 bucket is not public.
- S3 bucket policy that allows CloudFront to read objects.
- CloudFront access logging.
- S3 server access logging.
- AWS WAF rate limiting.
- Remote Terraform state stored in S3.
- GitHub Actions deployment automation.

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

Install:

- Git
- Terraform
- AWS CLI
- A GitHub account
- An AWS account

Verify tools:

```bash
git --version
terraform version
aws --version
```

Configure AWS CLI:

```bash
aws configure
```

Use:

```text
Default region: us-east-1
Default output format: json
```

This project uses `us-east-1` because CloudFront WAF resources must be created there.

## AWS IAM Setup

Create an IAM user or role for deployment.

The deployment identity needs access to:

- S3
- CloudFront
- WAFv2
- Terraform state bucket

For learning projects, `AdministratorAccess` is often used temporarily. For production, use least privilege.

GitHub repository secrets required:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
```

## Step 1: Clone or Fork

```bash
git clone <YOUR_REPOSITORY_URL>
cd <YOUR_REPOSITORY_FOLDER>
```

All Terraform commands are run from:

```text
S3/static-website-hosting
```

## Step 2: Create the Terraform Remote State Bucket

Terraform needs remote state so it remembers already-created AWS resources.

Without remote state, GitHub Actions may create a new S3 bucket and CloudFront distribution on every run.

Get your AWS account ID:

```bash
aws sts get-caller-identity --query Account --output text
```

Choose a globally unique state bucket name:

```text
<your-name>-static-website-tfstate-<aws-account-id>
```

Create the state bucket:

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

Do not delete this bucket. It stores Terraform's memory.

## Step 3: Configure Terraform Backend

Open:

```text
S3/static-website-hosting/main.tf
```

Update:

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

Current project backend:

```text
vaibhav-static-website-tfstate-285977275740
```

Anyone reusing this project must replace that bucket with their own state bucket.

## Step 4: Configure Variables

Open:

```text
S3/static-website-hosting/variables.tf
```

Current variables:

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

Terraform creates buckets like:

```text
your-name-static-website-bucket-origin-xxxxxxxx
your-name-static-website-bucket-logs-xxxxxxxx
```

The suffix stays stable after remote state is configured.

## Step 5: Add Website Files

Put website files here:

```text
S3/static-website-hosting/site/
```

Minimum file:

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

The workflow uploads this folder:

```bash
aws s3 sync ./site s3://${{ env.BUCKET_NAME }} --delete
```

`--delete` removes files from S3 that were removed locally.

## Step 6: Initialize and Validate Terraform

```bash
cd S3/static-website-hosting
terraform init
terraform fmt
terraform validate
```

Optional:

```bash
terraform plan
```

Expected validation result:

```text
Success! The configuration is valid.
```

## Step 7: GitHub Setup

The workflow must be located at:

```text
.github/workflows/deploy.yml
```

Add GitHub secrets:

1. Open your GitHub repository.
2. Go to **Settings**.
3. Go to **Secrets and variables**.
4. Open **Actions**.
5. Add:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
```

## Step 8: Deployment Flow

The workflow runs on pushes to `main` when infrastructure, workflow, or website files change.

It does:

1. Checks out the repository.
2. Authenticates to AWS.
3. Installs Terraform.
4. Runs `terraform init`.
5. Runs `terraform apply -auto-approve`.
6. Reads Terraform outputs.
7. Syncs `site/` files to S3.
8. Invalidates CloudFront cache.

Deployment command sequence inside GitHub Actions:

```bash
cd "S3/static-website-hosting"
terraform init
terraform apply -auto-approve
aws s3 sync ./site s3://<origin-bucket> --delete
aws cloudfront create-invalidation --distribution-id <distribution-id> --paths "/*"
```

## Step 9: Push and Deploy

```bash
git status
git add .
git commit -m "Deploy static website"
git push origin main
```

Then:

1. Open GitHub.
2. Go to **Actions**.
3. Open the latest workflow run.
4. Wait for success.

## Step 10: View the Website

Get the CloudFront URL:

```bash
cd S3/static-website-hosting
terraform output cloudfront_url
```

Example:

```text
https://dua88g8j3o5ks.cloudfront.net
```

You can also find it in AWS:

```text
CloudFront -> Distributions -> Distribution domain name
```

Use the CloudFront URL to view the site. The S3 bucket is private by design.

## Step 11: Confirm Active Resources

```bash
terraform output -raw origin_bucket_name
terraform output -raw cloudfront_distribution_id
terraform output -raw cloudfront_url
```

Find the logs bucket:

```bash
terraform state show aws_s3_bucket.logs
```

Look for:

```text
bucket = "<logs-bucket-name>"
```

## Useful AWS S3 Commands

Set variables first.

Bash:

```bash
cd S3/static-website-hosting
ORIGIN_BUCKET=$(terraform output -raw origin_bucket_name)
DIST_ID=$(terraform output -raw cloudfront_distribution_id)
LOGS_BUCKET=$(terraform state show aws_s3_bucket.logs | awk -F'"' '/bucket +=/ {print $2; exit}')
```

PowerShell:

```powershell
cd S3/static-website-hosting
$ORIGIN_BUCKET = terraform output -raw origin_bucket_name
$DIST_ID = terraform output -raw cloudfront_distribution_id
$LOGS_BUCKET = (terraform state show aws_s3_bucket.logs | Select-String 'bucket\s+=' | Select-Object -First 1).ToString().Split('"')[1]
```

### List Buckets and Objects

List all buckets:

```bash
aws s3 ls
```

List website bucket files:

```bash
aws s3 ls s3://$ORIGIN_BUCKET
```

List recursively:

```bash
aws s3 ls s3://$ORIGIN_BUCKET --recursive
```

PowerShell:

```powershell
aws s3 ls s3://$ORIGIN_BUCKET --recursive
```

### Upload Files

Upload one file:

```bash
aws s3 cp ./site/index.html s3://$ORIGIN_BUCKET/index.html
```

Upload an image:

```bash
aws s3 cp ./site/profile.jpg s3://$ORIGIN_BUCKET/profile.jpg
```

Upload the whole website:

```bash
aws s3 sync ./site s3://$ORIGIN_BUCKET --delete
```

Upload HTML with no-cache headers:

```bash
aws s3 cp ./site/index.html s3://$ORIGIN_BUCKET/index.html \
  --cache-control "no-cache, no-store, must-revalidate" \
  --content-type "text/html"
```

Upload an image with longer browser cache:

```bash
aws s3 cp ./site/profile.jpg s3://$ORIGIN_BUCKET/profile.jpg \
  --cache-control "public, max-age=86400" \
  --content-type "image/jpeg"
```

After manual uploads, invalidate CloudFront:

```bash
aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/*"
```

### Download Files

Download one file:

```bash
aws s3 cp s3://$ORIGIN_BUCKET/index.html ./downloaded-index.html
```

Download the full website:

```bash
aws s3 sync s3://$ORIGIN_BUCKET ./downloaded-site
```

Download one folder or prefix:

```bash
aws s3 sync s3://$ORIGIN_BUCKET/assets ./downloaded-assets
```

### Inspect Metadata

Check object metadata:

```bash
aws s3api head-object --bucket $ORIGIN_BUCKET --key index.html
```

Check image metadata:

```bash
aws s3api head-object --bucket $ORIGIN_BUCKET --key profile.jpg
```

Useful fields:

```text
ContentType
CacheControl
LastModified
ETag
ContentLength
```

### Delete Objects

Delete one object:

```bash
aws s3 rm s3://$ORIGIN_BUCKET/old-file.html
```

Delete a folder or prefix:

```bash
aws s3 rm s3://$ORIGIN_BUCKET/old-assets/ --recursive
```

Use delete commands carefully. Normal deployments already sync local `site/` to S3.

### Presigned URLs

Create a temporary download URL valid for 15 minutes:

```bash
aws s3 presign s3://$ORIGIN_BUCKET/index.html --expires-in 900
```

Normal public viewing should use CloudFront, not presigned S3 URLs.

## Useful CloudFront Commands

List distributions:

```bash
aws cloudfront list-distributions \
  --query "DistributionList.Items[].{Id:Id,Domain:DomainName,Enabled:Enabled,Origin:Origins.Items[0].DomainName}" \
  --output table
```

Create invalidation:

```bash
aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/*"
```

Check distribution:

```bash
aws cloudfront get-distribution --id $DIST_ID
```

Check logging config:

```bash
aws cloudfront get-distribution-config \
  --id $DIST_ID \
  --query "DistributionConfig.Logging" \
  --output table
```

## Caching

CloudFront cache settings in `main.tf`:

```hcl
min_ttl     = 0
default_ttl = 3600
max_ttl     = 86400
```

Meaning:

```text
Default cache: 1 hour
Maximum cache: 1 day
```

Every deployment runs:

```bash
aws cloudfront create-invalidation --distribution-id <distribution-id> --paths "/*"
```

So deployed changes should become visible after invalidation completes.

## Logging

### CloudFront Logs

Configured prefix:

```text
cloudfront-edge-logs/
```

List logs:

```bash
aws s3 ls s3://$LOGS_BUCKET/cloudfront-edge-logs/ --recursive
```

Download logs:

```bash
aws s3 sync s3://$LOGS_BUCKET/cloudfront-edge-logs/ ./cloudfront-logs
```

Extract a `.gz` log on Linux/macOS/Git Bash:

```bash
gzip -dk ./cloudfront-logs/<log-file-name>.gz
```

On Windows, download the `.gz` file and extract it using 7-Zip or another archive tool.

### S3 Access Logs

Configured prefix:

```text
s3-access-logs/
```

List logs:

```bash
aws s3 ls s3://$LOGS_BUCKET/s3-access-logs/ --recursive
```

Download logs:

```bash
aws s3 sync s3://$LOGS_BUCKET/s3-access-logs/ ./s3-access-logs
```

Logs can take several minutes to appear.

## Security

The S3 origin bucket is private.

Public access is blocked:

```hcl
block_public_acls       = true
block_public_policy     = true
ignore_public_acls      = true
restrict_public_buckets = true
```

CloudFront accesses S3 through Origin Access Control:

```hcl
origin_access_control_origin_type = "s3"
signing_behavior                  = "always"
signing_protocol                  = "sigv4"
```

The bucket policy allows the CloudFront service principal only.

## WAF Protection

The project creates a WAF Web ACL attached to CloudFront:

```hcl
scope = "CLOUDFRONT"
```

The rate limit rule blocks excessive requests from the same IP:

```hcl
rate_based_statement {
  limit              = 300
  aggregate_key_type = "IP"
}
```

## Troubleshooting

### `terraform: command not found`

Add Terraform setup to GitHub Actions:

```yaml
- name: Install Terraform CLI
  uses: hashicorp/setup-terraform@v3
  with:
    terraform_wrapper: false
```

### Terraform creates new buckets every run

Remote state is missing or misconfigured. Configure the S3 backend and run:

```bash
terraform init -reconfigure
```

### `Reference to undeclared resource`

Check that Terraform references match declared resource names.

Example:

```hcl
policy = data.aws_iam_policy_document.oac_policy_doc.json
```

must match:

```hcl
data "aws_iam_policy_document" "oac_policy_doc" {}
```

### `NoSuchBucket` during sync

Make sure the workflow uses:

```bash
terraform output -raw origin_bucket_name
```

### Old content still appears

Check:

```text
CloudFront -> Distribution -> Invalidations
```

Wait until invalidation is complete, then hard refresh the browser.

### Direct S3 URL does not work

Expected. The bucket is private. Use the CloudFront URL.

## Cleanup Old Duplicate Resources

If the project was deployed before remote state was configured, duplicate buckets and CloudFront distributions may exist.

Keep:

- Active origin bucket from `terraform output -raw origin_bucket_name`
- Active CloudFront distribution from `terraform output -raw cloudfront_distribution_id`
- Logs bucket from `terraform state show aws_s3_bucket.logs`
- Terraform state bucket from the backend block

Delete only old duplicate buckets and distributions that Terraform does not manage.

CloudFront deletion:

1. Disable old distribution.
2. Wait until status becomes `Deployed`.
3. Delete old distribution.

S3 bucket deletion:

1. Empty old bucket.
2. Delete old bucket.

Never delete the Terraform state bucket unless you are permanently retiring the project.

## Destroy the Project

To remove Terraform-managed infrastructure:

```bash
cd S3/static-website-hosting
terraform destroy
```

After destroy, decide manually whether to keep or delete the Terraform state bucket.

## Maintenance Checklist

For future website updates:

1. Edit files in `S3/static-website-hosting/site/`.
2. Commit and push to `main`.
3. Watch GitHub Actions.
4. Open the CloudFront URL.
5. Check invalidation if old content appears.
6. Check logs bucket if traffic logs are needed.

For documentation-only updates:

1. Edit `README.md`.
2. Commit and push.
3. The workflow should not redeploy if only README files changed.

## Current Project Values

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
