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
