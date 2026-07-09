terraform {
  backend "s3" {
    bucket       = "vaibhav-terraform-state-285977275740"
    key          = "capstone-smartwatt/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "SmartWatt"
      Environment = var.environment
      ManagedBy   = "Terraform"
      Owner       = "Vaibhav"
    }
  }
}

resource "random_id" "suffix" {
  byte_length = 4
}


resource "aws_dynamodb_table" "telemetry_table" {
  name         = "${var.project_name}-telemetry-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }
}


resource "aws_cognito_user_pool" "user_pool" {
  name = "${var.project_name}-user-pool-${var.environment}"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
  }

  schema {
    name                = "role"
    attribute_data_type = "String"
    mutable             = true
    required            = false
    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  schema {
    name                = "department"
    attribute_data_type = "String"
    mutable             = true
    required            = false
    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  schema {
    name                = "project"
    attribute_data_type = "String"
    mutable             = true
    required            = false
    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  schema {
    name                = "company"
    attribute_data_type = "String"
    mutable             = true
    required            = false
    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }
}

resource "aws_cognito_user_pool_client" "client" {
  name            = "${var.project_name}-client-${var.environment}"
  user_pool_id    = aws_cognito_user_pool.user_pool.id
  generate_secret = false
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]
  read_attributes  = ["email", "custom:role", "custom:department", "custom:project", "custom:company"]
  write_attributes = ["email", "custom:role", "custom:department", "custom:project", "custom:company"]
}

resource "aws_cognito_user_group" "user" {
  name         = "User"
  user_pool_id = aws_cognito_user_pool.user_pool.id
  description  = "Standard users submitting device telemetry logs"
}

resource "aws_cognito_user_group" "admin" {
  name         = "Admin"
  user_pool_id = aws_cognito_user_pool.user_pool.id
  description  = "Administrators auditing billing logs and power surges"
}

resource "aws_cognito_user" "admin_user" {
  user_pool_id = aws_cognito_user_pool.user_pool.id
  username     = "vaibhavsp16@gmail.com"
  password     = "Vaibhav@123"

  attributes = {
    email             = "vaibhavsp16@gmail.com"
    email_verified    = "true"
    "custom:role"       = "Admin"
    "custom:department" = "DevOps-SLA-Audit"
    "custom:project"    = "ServerWatch-APM"
    "custom:company"    = "TringApps"
  }

  message_action = "SUPPRESS"

}

resource "aws_cognito_user_in_group" "admin_bind" {
  user_pool_id = aws_cognito_user_pool.user_pool.id
  username     = aws_cognito_user.admin_user.username
  group_name   = aws_cognito_user_group.admin.name
}


resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project_name}-dlq-${var.environment}"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "telemetry_queue" {
  name                      = "${var.project_name}-queue-${var.environment}"
  message_retention_seconds = 86400 # 1 day
  visibility_timeout_seconds = 60    # Must be >= lambda timeout

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sns_topic" "alerts_topic" {
  name = "${var.project_name}-alerts-${var.environment}"
}

resource "aws_sns_topic_subscription" "email_subscription" {
  topic_arn = aws_sns_topic.alerts_topic.arn
  protocol  = "email"
  endpoint  = var.sns_alert_email
}


resource "aws_s3_bucket" "hosting_bucket" {
  bucket        = "${var.project_name}-hosting-${var.environment}-${random_id.suffix.hex}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "hosting_bucket_block" {
  bucket = aws_s3_bucket.hosting_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "frontend_upload" {
  bucket       = aws_s3_bucket.hosting_bucket.id
  key          = "index.html"
  source       = "${path.module}/frontend/index.html"
  content_type = "text/html"
  etag         = filemd5("${path.module}/frontend/index.html")
}

resource "aws_s3_object" "config_js" {
  bucket       = aws_s3_bucket.hosting_bucket.id
  key          = "config.js"
  content      = <<EOF
window.CONFIG = {
  userPoolId: "${aws_cognito_user_pool.user_pool.id}",
  clientId: "${aws_cognito_user_pool_client.client.id}",
  apiUrl: "${aws_api_gateway_stage.api_stage.invoke_url}",
  region: "${var.aws_region}",
  geminiApiKey: "${var.gemini_api_key}"
};
EOF
  content_type = "application/javascript"
}

resource "aws_cloudfront_origin_access_control" "oac" {
  name                              = "${var.project_name}-oac-${var.environment}"
  description                       = "OAC for static frontend hosting S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "cdn" {
  origin {
    domain_name              = aws_s3_bucket.hosting_bucket.bucket_regional_domain_name
    origin_id                = "S3-${aws_s3_bucket.hosting_bucket.id}"
    origin_access_control_id = aws_cloudfront_origin_access_control.oac.id
  }

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.hosting_bucket.id}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name = "${var.project_name}-cdn-${var.environment}"
  }
}

resource "aws_s3_bucket_policy" "cloudfront_access_policy" {
  bucket = aws_s3_bucket.hosting_bucket.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCloudFrontServicePrincipalReadOnly"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.hosting_bucket.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.cdn.arn
          }
        }
      }
    ]
  })
}


data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingestion_role" {
  name               = "${var.project_name}-ingestion-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "ingestion_logs" {
  role       = aws_iam_role.ingestion_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "ingestion_sqs" {
  name        = "${var.project_name}-ingestion-sqs-${var.environment}"
  description = "Allows pushing logs to SQS queue"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.telemetry_queue.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ingestion_sqs_attach" {
  role       = aws_iam_role.ingestion_role.name
  policy_arn = aws_iam_policy.ingestion_sqs.arn
}

resource "aws_iam_role" "processor_role" {
  name               = "${var.project_name}-processor-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "processor_logs" {
  role       = aws_iam_role.processor_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "processor_perms" {
  name        = "${var.project_name}-processor-perms-${var.environment}"
  description = "Allows reading from SQS, writing to DynamoDB, and publishing to SNS"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.telemetry_queue.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.telemetry_table.arn
      },
      {
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = aws_sns_topic.alerts_topic.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "processor_perms_attach" {
  role       = aws_iam_role.processor_role.name
  policy_arn = aws_iam_policy.processor_perms.arn
}

resource "aws_iam_role" "auditor_role" {
  name               = "${var.project_name}-auditor-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "auditor_logs" {
  role       = aws_iam_role.auditor_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "auditor_perms" {
  name        = "${var.project_name}-auditor-perms-${var.environment}"
  description = "Allows reading/writing to DynamoDB and publishing alerts to SNS"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Scan",
          "dynamodb:Query",
          "dynamodb:PutItem",
          "dynamodb:GetItem"
        ]
        Resource = aws_dynamodb_table.telemetry_table.arn
      },
      {
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = aws_sns_topic.alerts_topic.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "auditor_perms_attach" {
  role       = aws_iam_role.auditor_role.name
  policy_arn = aws_iam_policy.auditor_perms.arn
}


data "archive_file" "ingestion_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/ingestion.py"
  output_path = "${path.module}/lambda/ingestion.zip"
}

data "archive_file" "processor_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/processor.py"
  output_path = "${path.module}/lambda/processor.zip"
}

data "archive_file" "auditor_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/auditor.py"
  output_path = "${path.module}/lambda/auditor.zip"
}

resource "aws_lambda_function" "ingestion_func" {
  filename         = data.archive_file.ingestion_zip.output_path
  function_name    = "${var.project_name}-ingestion-${var.environment}"
  role             = aws_iam_role.ingestion_role.arn
  handler          = "ingestion.lambda_handler"
  runtime          = "python3.9"
  source_code_hash = data.archive_file.ingestion_zip.output_base64sha256
  timeout          = 10

  environment {
    variables = {
      QUEUE_URL = aws_sqs_queue.telemetry_queue.id
    }
  }
}

resource "aws_lambda_function" "processor_func" {
  filename         = data.archive_file.processor_zip.output_path
  function_name    = "${var.project_name}-processor-${var.environment}"
  role             = aws_iam_role.processor_role.arn
  handler          = "processor.lambda_handler"
  runtime          = "python3.9"
  source_code_hash = data.archive_file.processor_zip.output_base64sha256
  timeout          = 15

  environment {
    variables = {
      DYNAMODB_TABLE_NAME   = aws_dynamodb_table.telemetry_table.name
      SNS_TOPIC_ARN         = aws_sns_topic.alerts_topic.arn
      LATENCY_THRESHOLD_MS  = "250"
      CPU_THRESHOLD_PCT     = "90"
      MEMORY_THRESHOLD_PCT  = "95"
    }
  }
}

resource "aws_lambda_function" "auditor_func" {
  filename         = data.archive_file.auditor_zip.output_path
  function_name    = "${var.project_name}-auditor-${var.environment}"
  role             = aws_iam_role.auditor_role.arn
  handler          = "auditor.lambda_handler"
  runtime          = "python3.9"
  source_code_hash = data.archive_file.auditor_zip.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.telemetry_table.name
      SNS_TOPIC_ARN       = aws_sns_topic.alerts_topic.arn
      SURGE_LIMIT_WATTS   = "5000"
    }
  }
}

resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.telemetry_queue.arn
  function_name    = aws_lambda_function.processor_func.arn
  batch_size       = 10
}


resource "aws_iam_role" "scheduler_role" {
  name = "${var.project_name}-scheduler-role-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "scheduler_lambda_invoke" {
  name = "${var.project_name}-scheduler-invoke-${var.environment}"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = aws_lambda_function.auditor_func.arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "scheduler_attach" {
  role       = aws_iam_role.scheduler_role.name
  policy_arn = aws_iam_policy.scheduler_lambda_invoke.arn
}

resource "aws_scheduler_schedule" "daily_audit" {
  name       = "${var.project_name}-daily-audit-${var.environment}"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "cron(0 9 * * ? *)" # Run every day at 9:00 AM UTC

  target {
    arn      = aws_lambda_function.auditor_func.arn
    role_arn = aws_iam_role.scheduler_role.arn
    input    = jsonencode({ "source" = "aws.scheduler" })
  }
}

resource "aws_lambda_permission" "allow_scheduler" {
  statement_id  = "AllowExecutionFromEventBridgeScheduler"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auditor_func.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.daily_audit.arn
}


resource "aws_api_gateway_rest_api" "api" {
  name        = "SmartWattREST_API"
  description = "Managed via Terraform - IoT Telemetry System APIs"
}

resource "aws_api_gateway_authorizer" "cognito" {
  name          = "CognitoUserAuthorizer"
  type          = "COGNITO_USER_POOLS"
  rest_api_id   = aws_api_gateway_rest_api.api.id
  provider_arns = [aws_cognito_user_pool.user_pool.arn]
}

resource "aws_api_gateway_resource" "telemetry" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_rest_api.api.root_resource_id
  path_part   = "telemetry"
}

resource "aws_api_gateway_method" "telemetry_post" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.telemetry.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "telemetry_integration" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.telemetry.id
  http_method             = aws_api_gateway_method.telemetry_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.ingestion_func.invoke_arn
}

resource "aws_api_gateway_resource" "audit" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_rest_api.api.root_resource_id
  path_part   = "audit"
}

resource "aws_api_gateway_method" "audit_get" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.audit.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_integration" "audit_integration" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.audit.id
  http_method             = aws_api_gateway_method.audit_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.auditor_func.invoke_arn
}

resource "aws_api_gateway_method" "telemetry_options" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.telemetry.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "telemetry_options_integration" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.telemetry.id
  http_method             = aws_api_gateway_method.telemetry_options.http_method
  type                    = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "telemetry_options_response" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.telemetry.id
  http_method = aws_api_gateway_method.telemetry_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "telemetry_options_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.telemetry.id
  http_method = aws_api_gateway_method.telemetry_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
  depends_on = [aws_api_gateway_integration.telemetry_options_integration]
}

resource "aws_api_gateway_method" "audit_options" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.audit.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "audit_options_integration" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.audit.id
  http_method             = aws_api_gateway_method.audit_options.http_method
  type                    = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "audit_options_response" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.audit.id
  http_method = aws_api_gateway_method.audit_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "audit_options_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.audit.id
  http_method = aws_api_gateway_method.audit_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
  depends_on = [aws_api_gateway_integration.audit_options_integration]
}

resource "aws_lambda_permission" "api_allow_ingestion" {
  statement_id  = "AllowExecutionFromAPIGatewayIngestion"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion_func.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_allow_auditor" {
  statement_id  = "AllowExecutionFromAPIGatewayAuditor"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auditor_func.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*"
}

resource "aws_api_gateway_deployment" "api_deploy" {
  rest_api_id = aws_api_gateway_rest_api.api.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.telemetry.id,
      aws_api_gateway_method.telemetry_post.id,
      aws_api_gateway_integration.telemetry_integration.id,
      aws_api_gateway_resource.audit.id,
      aws_api_gateway_method.audit_get.id,
      aws_api_gateway_integration.audit_integration.id,
      aws_api_gateway_method.telemetry_options.id,
      aws_api_gateway_integration.telemetry_options_integration.id,
      aws_api_gateway_method.audit_options.id,
      aws_api_gateway_integration.audit_options_integration.id
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
  
  depends_on = [
    aws_api_gateway_integration.telemetry_integration,
    aws_api_gateway_integration.audit_integration,
    aws_api_gateway_integration.telemetry_options_integration,
    aws_api_gateway_integration.audit_options_integration,
    aws_api_gateway_integration_response.telemetry_options_integration_response,
    aws_api_gateway_integration_response.audit_options_integration_response
  ]
}

resource "aws_api_gateway_stage" "api_stage" {
  deployment_id = aws_api_gateway_deployment.api_deploy.id
  rest_api_id   = aws_api_gateway_rest_api.api.id
  stage_name    = var.environment
}
