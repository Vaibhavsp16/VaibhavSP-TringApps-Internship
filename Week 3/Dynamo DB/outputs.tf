output "deployed_s3_bucket" {
  description = "The live ingest data system bucket name"
  value       = aws_s3_bucket.upload_bucket.id
}

output "active_dynamodb_table" {
  description = "The active persistent storage table tracking engine rows"
  value       = aws_dynamodb_table.feedback_table.name
}

output "api_gateway_invoke_url" {
  description = "The live public entrypoint path URL for testing your CRUD API endpoints"
  value       = "${aws_api_gateway_stage.api_stage.invoke_url}/${aws_api_gateway_resource.feedback_resource.path_part}"
}