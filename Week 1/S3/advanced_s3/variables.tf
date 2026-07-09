variable "bucket_name" {
  description = "The name of the S3 bucket to create"
  type        = string
  default     = "vaibhav-s3-advanced-vault-1612"
}

variable "glacier_transition_days" {
    description = "Number of days after which objects will transition to Glacier"
    type        = number
    default     = 30
}

variable "expiration_days" {
    description = "Number of days after which objects will expire"
    type        = number
    default     = 365
}

variable "object_lock_days" {
    description = "Number of days for which object lock will be enabled in WORM complaince"
    type        = number
    default     = 7
}