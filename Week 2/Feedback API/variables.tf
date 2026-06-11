variable "aws_region" {
  description = "The AWS region to deploy resources in."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "The deployment environment (e.g., dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "The name of the project for tagging resources."
  type        = string
  default     = "student-feedback"
}

variable "admin_password" {
  description = "The password for the admin Cognito user."
  type        = string
  default     = "Vaibhav@123"
}
