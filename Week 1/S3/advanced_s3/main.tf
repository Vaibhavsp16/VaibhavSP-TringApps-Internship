resource "aws_s3_bucket" "advanced_vault" {
  bucket = var.bucket_name
  object_lock_enabled = true
}

resource "aws_s3_bucket_versioning" "vault_versioning" {
  bucket = aws_s3_bucket.advanced_vault.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "vault_lifecycle" {
  bucket = aws_s3_bucket.advanced_vault.id

  rule {
    id     = "archive-and-cleanup"
    status = "Enabled"

    transition {
      days          = var.glacier_transition_days
      storage_class = "GLACIER"
    }

    expiration {
      days = var.expiration_days
    }
  }
}

resource "aws_s3_bucket_object_lock_configuration" "vault_lock" {
  bucket = aws_s3_bucket.advanced_vault.id

    rule {
      default_retention {
        mode = "GOVERNANCE"
        days = var.object_lock_days
    }
  }
}