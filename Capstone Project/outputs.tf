output "dynamodb_table_name" {
  value       = aws_dynamodb_table.telemetry_table.name
  description = "The name of the DynamoDB telemetry table"
}

output "cognito_user_pool_id" {
  value       = aws_cognito_user_pool.user_pool.id
  description = "The ID of the Cognito User Pool"
}

output "cognito_client_id" {
  value       = aws_cognito_user_pool_client.client.id
  description = "The ID of the Cognito User Pool Client"
}

output "s3_hosting_bucket_name" {
  value       = aws_s3_bucket.hosting_bucket.id
  description = "The S3 bucket name hosting the frontend dashboard"
}

output "cloudfront_url" {
  value       = "https://${aws_cloudfront_distribution.cdn.domain_name}"
  description = "The clickable CloudFront CDN dashboard URL"
}

output "api_endpoint_url" {
  value       = aws_api_gateway_stage.api_stage.invoke_url
  description = "The REST API Gateway execution URL endpoint"
}
