output "upload_bucket_name" {
  description = "The name of the upload S3 bucket"
  value       = aws_s3_bucket.upload_bucket.id
}

output "processed_bucket_name" {
  description = "The name of the processed S3 bucket"
  value       = aws_s3_bucket.processed_bucket.id
}

output "user_pool_id" {
  description = "The Cognito User Pool ID"
  value       = aws_cognito_user_pool.user_pool.id
}

output "app_client_id" {
  description = "The Cognito App Client ID"
  value       = aws_cognito_user_pool_client.user_pool_client.id
}

output "api_url" {
  description = "The URL of the protected endpoint"
  value       = "${aws_api_gateway_stage.api_stage.invoke_url}/${aws_api_gateway_resource.upload_url_resource.path_part}"
}

output "sns_topic_arn" {
  description = "The ARN of the SNS topic for completion alerts"
  value       = aws_sns_topic.completion_topic.arn
}

output "sqs_queue_url" {
  description = "The URL of the metadata SQS queue"
  value       = aws_sqs_queue.metadata_queue.id
}

output "cloudfront_url" {
  description = "The URL of the CloudFront distribution hosting the frontend"
  value       = "https://${aws_cloudfront_distribution.frontend_distribution.domain_name}"
}
