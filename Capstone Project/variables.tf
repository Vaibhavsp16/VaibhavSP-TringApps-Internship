variable "aws_region" {
  description = "The AWS region to deploy resources into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "The deployment stage environment tag"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Prefix name for all resources in the stack"
  type        = string
  default     = "smartwatt"
}

variable "sns_alert_email" {
  description = "Email address to receive daily audits and surge warning alerts"
  type        = string
  default     = "vaibhavsp16@gmail.com"
}

variable "gemini_api_key" {
  description = "Google AI Studio Gemini API Key for log analytics"
  type        = string
  default     = ""
  sensitive   = true
}

