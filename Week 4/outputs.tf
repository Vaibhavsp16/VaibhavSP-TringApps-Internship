output "user_pool_id" {
    description = "The ID of the Cognito User Pool"
    value = aws_cognito_user_pool.user_pool.id
}

output "app_client_id" {
    description = "The ID of the Cognito User Pool Client"
    value = aws_cognito_user_pool_client.user_pool_client.id
}

output "api_url" {
    description = "The URL of the API"
    value = "${aws_api_gateway_stage.api_stage.invoke_url}/${aws_api_gateway_resource.secure_resource.path_part}"
}

output "sns_topic_arn" {
    description = "The ARN of the SNS topic"
    value = aws_sns_topic.sns_topic.arn
}

output "sqs_queue_url" {
  description = "The URL of the SQS Queue"
  value       = aws_sqs_queue.queue.url
}

output "sqs_queue_arn" {
  description = "The ARN of the SQS Queue"
  value       = aws_sqs_queue.queue.arn
}
