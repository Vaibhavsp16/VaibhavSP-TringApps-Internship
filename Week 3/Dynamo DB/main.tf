provider "aws" {
  region = var.aws_region
}

resource "aws_dynamodb_table" "feedback_table" {
  name         = var.dynamodb_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "feedback_id"

  attribute {
    name = "feedback_id"
    type = "S"
  }
}

resource "aws_s3_bucket" "upload_bucket" {
  bucket        = var.upload_bucket_name
  force_destroy = true
}

resource "aws_iam_role" "s3_lambda_role" {
  name = "${var.project_name}-s3-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "s3_lambda_logs" {
  role       = aws_iam_role.s3_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "s3_lambda_s3_read" {
  role       = aws_iam_role.s3_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}

resource "aws_iam_role_policy_attachment" "s3_lambda_db_write" {
  role       = aws_iam_role.s3_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
}

data "archive_file" "s3_lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/process_upload.py"
  output_path = "${path.module}/process_upload.zip"
}

resource "aws_lambda_function" "s3_processor" {
  filename         = data.archive_file.s3_lambda_zip.output_path
  function_name    = "${var.project_name}-s3-function"
  role             = aws_iam_role.s3_lambda_role.arn
  handler          = "process_upload.lambda_handler"
  source_code_hash = data.archive_file.s3_lambda_zip.output_base64sha256
  runtime          = "python3.9"

  environment {
    variables = { DYNAMODB_TABLE_NAME = aws_dynamodb_table.feedback_table.name }
  }
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowExecutionFromS3Bucket"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.s3_processor.arn
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.upload_bucket.arn
}

resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.upload_bucket.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.s3_processor.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "incoming/"
  }
  depends_on = [aws_lambda_permission.allow_s3]
}

resource "aws_iam_role" "api_lambda_role" {
  name = "${var.project_name}-api-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "api_lambda_logs" {
  role       = aws_iam_role.api_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "api_lambda_db" {
  role       = aws_iam_role.api_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
}

data "archive_file" "api_lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/api_backend.py"
  output_path = "${path.module}/api_backend.zip"
}

resource "aws_lambda_function" "api_backend" {
  filename         = data.archive_file.api_lambda_zip.output_path
  function_name    = "${var.project_name}-api-function"
  role             = aws_iam_role.api_lambda_role.arn
  handler          = "api_backend.lambda_handler"
  source_code_hash = data.archive_file.api_lambda_zip.output_base64sha256
  runtime          = "python3.9"

  environment {
    variables = { DYNAMODB_TABLE_NAME = aws_dynamodb_table.feedback_table.name }
  }
}

resource "aws_api_gateway_rest_api" "feedback_api" {
  name        = "FeedbackREST_API"
  description = "Managed via Terraform - Unifies the backend CRUD architecture pipelines"
}

resource "aws_api_gateway_resource" "feedback_resource" {
  rest_api_id = aws_api_gateway_rest_api.feedback_api.id
  parent_id   = aws_api_gateway_rest_api.feedback_api.root_resource_id
  path_part   = "feedback"
}

resource "aws_api_gateway_method" "any_method" {
  rest_api_id   = aws_api_gateway_rest_api.feedback_api.id
  resource_id   = aws_api_gateway_resource.feedback_resource.id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "lambda_integration" {
  rest_api_id             = aws_api_gateway_rest_api.feedback_api.id
  resource_id             = aws_api_gateway_resource.feedback_resource.id
  http_method             = aws_api_gateway_method.any_method.http_method
  integration_http_method = "POST" 
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api_backend.invoke_arn
}

resource "aws_lambda_permission" "allow_api_gateway" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_backend.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.feedback_api.execution_arn}/*/*/*"
}

resource "aws_api_gateway_deployment" "api_deployment" {
  rest_api_id = aws_api_gateway_rest_api.feedback_api.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.feedback_resource.id,
      aws_api_gateway_method.any_method.id,
      aws_api_gateway_integration.lambda_integration.id,
    ]))
  }

  lifecycle { create_before_destroy = true }
  depends_on = [aws_api_gateway_integration.lambda_integration]
}

resource "aws_api_gateway_stage" "api_stage" {
  deployment_id = aws_api_gateway_deployment.api_deployment.id
  rest_api_id   = aws_api_gateway_rest_api.feedback_api.id
  stage_name    = var.api_stage_name
}