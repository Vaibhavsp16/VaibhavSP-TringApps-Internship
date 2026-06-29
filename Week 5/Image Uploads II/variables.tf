variable "upload_bucket_prefix" {
  description = "Prefix for the raw uploads S3 bucket"
  type        = string
  default     = "week4-photo-uploads"
}

variable "processed_bucket_prefix" {
  description = "Prefix for the processed images S3 bucket"
  type        = string
  default     = "week4-photo-processed"
}

variable "aws_region" {
  description = "The AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "The deployment environment"
  type        = string
  default     = "dev"
}

variable "user_pool_name" {
  description = "Name of the Cognito User Pool"
  type        = string
  default     = "img-pipeline-user-pool"
}

variable "app_client_name" {
  description = "Name of the App Client"
  type        = string
  default     = "img-pipeline-app-client"
}

variable "sns_subscription_email" {
  description = "The email address to receive completion notifications"
  type        = string
  default     = "vaibhavsp16@gmail.com"
}
