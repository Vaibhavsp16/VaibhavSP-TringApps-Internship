variable "aws_region" {
  description = "The primary AWS region for resource deployment"
  type = string
  default = "us-east-1"
}

variable "bucket_prefix" {
    description = "A prefix for the S3 bucket name to ensure uniqueness"
    type = string
    default = "cloudfront-webapp-bucket"
}