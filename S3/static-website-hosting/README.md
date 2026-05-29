# Cloud Infrastructure Engineering — Verification Manual

## 1. Automated Pipeline Validation
1. Commit and push your local directory changes to your GitHub `main` branch.
2. Navigate to your repository's **Actions** tab to watch the automated worker execute your build runner.
3. Once completed, extract the live endpoint from the pipeline logs and open it in your browser to verify delivery.

## 2. Advanced S3 Operations Verification

### Presigned URL Generation Flow
To generate a secure, temporary external link allowing outside vendors to upload or download assets directly without an IAM profile, run this sequence in your local environment terminal:

```bash
# Generate a temporary download link valid for 15 minutes (900 seconds)
aws s3 presign s3://<YOUR_BUCKET_NAME>/index.html --expires-in 900