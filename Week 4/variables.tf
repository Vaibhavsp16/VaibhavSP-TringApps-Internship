variable "aws_region" {
    description = "The AWS region where Cognito resources will be created."
    type = string
    default = "us-east-1"
}

variable "environment" {
    description = "The deployment environment"
    type = string
    default = "dev"
}

variable "user_pool_name" {
    description = "Name of the Cognito User Pool"
    type = string
    default = "week4-user-pool"
}

variable "app_client_name" {
    description = "Name of the App Client"
    type = string
    default = "week4-app-client"
}

variable "sns_subscription_email" {
    description = "Email address to subscribe to SNS notifications"
    type = string
    default = "vaibhavsp16@gmail.com"
}
