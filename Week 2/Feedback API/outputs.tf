output "dynamo_table_name" {
  description = "The name of the DynamoDB table created for feedback storage."
  value = aws_dynamodb_table.feedback_table.name
}

output "cognito_user_pool_id" {
  description = "The ID of the Cognito User Pool created for student authentication."
  value = aws_cognito_user_pool.student_pool.id
}

output "cognito_client_id" {
  description = "The Client ID of the Cognito User Pool Client for authentication."
  value = aws_cognito_user_pool_client.student_client.id
}

output "live_api_url" {
  description = "The URL of the deployed API Gateway endpoint for the feedback API."
  value = "${aws_api_gateway_stage.api_stage.invoke_url}/feedback"
}

output "manager_live_website_url" {
  description = "The URL of the deployed API Gateway endpoint for the manager."
  value = "https://${aws_cloudfront_distribution.frontend_cdn.domain_name}"
}