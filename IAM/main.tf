# Configure the AWS Provider
provider "aws" {
  region = "us-east-1"
}

# Existing IAM user managed by Terraform
resource "aws_iam_user" "vaibhav_existing" {
  name = "Tring-VaibhavSP-Terraform"

  tags = {
    Environment = "Production"
    ManagedBy   = "Terraform"
  }
}

# New IAM user managed by Terraform
resource "aws_iam_user" "vaibhav_new" {
  name = "Tring-VaibhavSP-Terraform-2"

  tags = {
    Environment = "Production"
    ManagedBy   = "Terraform"
    Owner       = "Vaibhav"
  }
}

# Generate Programmatic Access Keys for the new user
resource "aws_iam_access_key" "vaibhav_new_keys" {
  user = aws_iam_user.vaibhav_new.name
}

output "access_key_id" {
  value = aws_iam_access_key.vaibhav_new_keys.id
}

output "secret_access_key" {
  value     = aws_iam_access_key.vaibhav_new_keys.secret
  sensitive = true # This hides the secret key in the terminal until you explicitly ask for it
}

# --- LAB 2: S3 BUCKET & FILE UPLOAD ---

# 1. Create the S3 Bucket
resource "aws_s3_bucket" "my_data_bucket" {
  bucket = "vaibhav-internship-data-bucket-1612" # <-- Change the numbers at the end!

  tags = {
    Environment = "Development"
    Purpose     = "Data Analytics Storage"
  }
}

# 2. Upload the Text File to the Bucket
resource "aws_s3_object" "file_upload" {
  bucket = aws_s3_bucket.my_data_bucket.id # Tells Terraform which bucket to target
  key    = "my_test_file.txt"              # The name the file will have inside AWS
  source = "my_test_file.txt"              # The local file we just created in Step 1
}