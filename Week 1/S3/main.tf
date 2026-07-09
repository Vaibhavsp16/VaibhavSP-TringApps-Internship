provider "aws" {
  region = "us-east-1"
}

# Bucket 1: Highly secure, private, encrypted, versioned bucket for code
module "secure_code_bucket" {
  source            = "./modules/s3_bucket"
  bucket_name       = "vaibhav-s3-bucket-1612"
  enable_versioning = true
  enable_encryption = true
}

# Bucket 2: Cheap, temporary, unversioned bucket for testing
module "temp_testing_bucket" {
  source            = "./modules/s3_bucket"
  bucket_name       = "vaibhav-temp-test-1612"
  enable_versioning = false
  enable_encryption = false
}