variable "aws_region" {
  description = "The target AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "A resource naming prefix to enforce standard naming conventions"
  type        = string
  default     = "intern-s3-processor"
}

variable "upload_bucket_name" {
  description = "The globally unique naming string for the ingest S3 storage element"
  type        = string
  default     = "vaibhav-intern-uploads-data-lake-123" 
}

variable "dynamodb_table_name" {
  description = "The database primary key access layer reference identifier"
  type        = string
  default     = "FeedbackAPI_Table"
}

variable "api_stage_name" {
  description = "The deployment stage deployment name for API Gateway"
  type        = string
  default     = "dev"
}