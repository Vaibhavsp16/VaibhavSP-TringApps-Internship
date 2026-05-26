variable "bucket_name" {
  description = "The globally unique name of the bucket"
  type        = string
}

variable "enable_versioning" {
  description = "Set to true to keep all versions of files"
  type        = bool
  default     = false
}

variable "enable_encryption" {
  description = "Set to true to encrypt the bucket with AES256"
  type        = bool
  default     = true
}