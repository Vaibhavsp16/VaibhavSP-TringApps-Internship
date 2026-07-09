# 1. The Core Bucket
resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name
}

# 2. Versioning Configuration
resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  
  versioning_configuration {
    # If the user sets the variable to true, Enable it. Otherwise, Suspend it.
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

# 3. Encryption Configuration
resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  # This uses a Terraform trick: if true, create 1 resource. If false, create 0.
  count  = var.enable_encryption ? 1 : 0
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}