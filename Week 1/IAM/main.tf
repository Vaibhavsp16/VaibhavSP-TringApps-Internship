provider "aws" {
  region = "us-east-1"
}

resource "aws_iam_user" "vaibhav_existing" {
  name = "Tring-VaibhavSP-Terraform"

  tags = {
    Environment = "Production"
    ManagedBy   = "Terraform"
  }
}

resource "aws_s3_bucket" "my_data_bucket" {
  bucket = "vaibhav-internship-data-bucket-1612"

  tags = {
    Environment = "Development"
    Purpose     = "Data Analytics Storage"
  }
}

resource "aws_s3_object" "file_upload" {
  bucket = aws_s3_bucket.my_data_bucket.id
  key    = "my_test_file.txt"
  source = "my_test_file.txt"
}

resource "aws_iam_policy" "s3_read_only_policy" {
  name        = "VaibhavS3ReadOnlyAccess"
  description = "Provides read-only access to the specific data analytics bucket"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject", 
          "s3:ListBucket" 
        ]
        Resource = [
          aws_s3_bucket.my_data_bucket.arn,     
          "${aws_s3_bucket.my_data_bucket.arn}/*" 
        ]
      }
    ]
  })
}

resource "aws_iam_user_policy_attachment" "attach_s3_policy" {
  user       = aws_iam_user.vaibhav_existing.name    
  policy_arn = aws_iam_policy.s3_read_only_policy.arn 
}