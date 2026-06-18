provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "upload_bucket" {
  bucket        = "${var.upload_bucket_prefix}-${data.aws_caller_identity.current.account_id}-${var.environment}"
  force_destroy = true 
}

resource "aws_s3_bucket_public_access_block" "upload_bucket_block" {
  bucket                  = aws_s3_bucket.upload_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "processed_bucket" {
  bucket        = "${var.processed_bucket_prefix}-${data.aws_caller_identity.current.account_id}-${var.environment}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "processed_bucket_block" {
  bucket                  = aws_s3_bucket.processed_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cognito_user_pool" "user_pool" {
  name = "${var.user_pool_name}-${var.environment}"

  username_attributes     = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  verification_message_template {
    email_subject        = "Verify your email"
    email_message        = "Hello, click on the link to verify your email: {####}"
    default_email_option = "CONFIRM_WITH_CODE"
  }

  # Custom attribute for user roles
  schema {
    attribute_data_type      = "String"
    developer_only_attribute = false
    mutable                  = true
    name                     = "role"
    required                 = false

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }
}

resource "aws_cognito_user_pool_client" "user_pool_client" {
  name         = "${var.app_client_name}-${var.environment}"
  user_pool_id = aws_cognito_user_pool.user_pool.id

  generate_secret = false
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]

  # Enforce read/write permissions for custom attributes (Mandatory Cognito setting)
  read_attributes  = ["email", "email_verified", "custom:role"]
  write_attributes = ["email", "custom:role"]
}

resource "aws_api_gateway_rest_api" "api" {
  name        = "img-pipeline-api-${var.environment}"
  description = "Protected API Gateway for Image Processing Pipeline"
}

resource "aws_api_gateway_authorizer" "cognito_authorizer" {
  name          = "cognito-authorizer"
  type          = "COGNITO_USER_POOLS"
  rest_api_id   = aws_api_gateway_rest_api.api.id
  provider_arns = [aws_cognito_user_pool.user_pool.arn]
}

resource "aws_api_gateway_resource" "upload_url_resource" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_rest_api.api.root_resource_id
  path_part   = "upload-url"
}

resource "aws_api_gateway_method" "upload_url_method" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.upload_url_resource.id
  http_method   = "POST"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito_authorizer.id
}

resource "aws_api_gateway_integration" "presigned_lambda_integration" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.upload_url_resource.id
  http_method             = aws_api_gateway_method.upload_url_method.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.presigned_lambda.invoke_arn
}

resource "aws_api_gateway_deployment" "api_deployment" {
  depends_on = [
    aws_api_gateway_integration.presigned_lambda_integration,
    aws_api_gateway_integration_response.options_integration_response
  ]
  rest_api_id = aws_api_gateway_rest_api.api.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.upload_url_resource.id,
      aws_api_gateway_method.upload_url_method.id,
      aws_api_gateway_integration.presigned_lambda_integration.id,
      aws_api_gateway_method.upload_url_options.id,
      aws_api_gateway_integration.upload_url_options_integration.id
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "api_stage" {
  deployment_id = aws_api_gateway_deployment.api_deployment.id
  rest_api_id   = aws_api_gateway_rest_api.api.id
  stage_name    = var.environment
}

resource "aws_lambda_permission" "apigw_presigned_lambda" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.presigned_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*"
}

resource "aws_iam_role" "presigned_lambda_role" {
  name = "img-pipeline-presigned-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "presigned_logs" {
  role       = aws_iam_role.presigned_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "presigned_s3_policy" {
  name        = "img-pipeline-presigned-s3-${var.environment}"
  description = "Allows pre-signing lambda role write permissions to S3"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.upload_bucket.arn}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "presigned_s3" {
  role       = aws_iam_role.presigned_lambda_role.name
  policy_arn = aws_iam_policy.presigned_s3_policy.arn
}

data "archive_file" "presigned_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/presigned.py"
  output_path = "${path.module}/presigned.zip"
}

resource "aws_lambda_function" "presigned_lambda" {
  filename      = data.archive_file.presigned_zip.output_path
  function_name = "img-pipeline-presigned-gen-${var.environment}"
  role          = aws_iam_role.presigned_lambda_role.arn
  handler       = "presigned.handler"
  runtime       = "python3.9"

  source_code_hash = data.archive_file.presigned_zip.output_base64sha256

  environment {
    variables = {
      UPLOAD_BUCKET = aws_s3_bucket.upload_bucket.id
    }
  }
}

resource "aws_sqs_queue" "metadata_queue" {
  name                      = "img-pipeline-metadata-queue-${var.environment}"
  delay_seconds             = 0
  max_message_size          = 262144
  message_retention_seconds = 86400
  receive_wait_time_seconds = 10 
}

resource "aws_iam_role" "extractor_role" {
  name = "img-pipeline-extractor-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "extractor_logs" {
  role       = aws_iam_role.extractor_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "extractor_policy" {
  name        = "img-pipeline-extractor-policy-${var.environment}"
  description = "Allows Extractor Lambda to read S3, query Rekognition, and write to SQS"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.upload_bucket.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["rekognition:DetectLabels"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.metadata_queue.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "extractor_policy_attach" {
  role       = aws_iam_role.extractor_role.name
  policy_arn = aws_iam_policy.extractor_policy.arn
}

data "archive_file" "extractor_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/extractor.py"
  output_path = "${path.module}/extractor.zip"
}

resource "aws_lambda_function" "extractor_lambda" {
  filename      = data.archive_file.extractor_zip.output_path
  function_name = "img-pipeline-extractor-${var.environment}"
  role          = aws_iam_role.extractor_role.arn
  handler       = "extractor.handler"
  runtime       = "python3.9"

  source_code_hash = data.archive_file.extractor_zip.output_base64sha256

  environment {
    variables = {
      QUEUE_URL = aws_sqs_queue.metadata_queue.id
    }
  }
}

resource "aws_lambda_permission" "allow_s3_bucket" {
  statement_id  = "AllowExecutionFromS3Bucket"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.extractor_lambda.arn
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.upload_bucket.arn
}

resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.upload_bucket.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.extractor_lambda.arn
    events              = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_lambda_permission.allow_s3_bucket]
}

resource "aws_sns_topic" "completion_topic" {
  name = "img-pipeline-completion-${var.environment}"
}

resource "aws_sns_topic_subscription" "email_sub" {
  topic_arn = aws_sns_topic.completion_topic.arn
  protocol  = "email"
  endpoint  = var.sns_subscription_email

  lifecycle {
    ignore_changes = [
      endpoint,
      protocol,
      topic_arn
    ]
  }
}

resource "aws_iam_role" "processor_role" {
  name = "img-pipeline-processor-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "processor_logs" {
  role       = aws_iam_role.processor_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "processor_sqs" {
  role       = aws_iam_role.processor_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole"
}

resource "aws_iam_policy" "processor_policy" {
  name        = "img-pipeline-processor-policy-${var.environment}"
  description = "Allows Processor Lambda to manage S3 buckets and publish to SNS"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.upload_bucket.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.processed_bucket.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = aws_sns_topic.completion_topic.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "processor_policy_attach" {
  role       = aws_iam_role.processor_role.name
  policy_arn = aws_iam_policy.processor_policy.arn
}

data "archive_file" "processor_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/processor.py"
  output_path = "${path.module}/processor.zip"
}

resource "aws_lambda_function" "processor_lambda" {
  filename      = data.archive_file.processor_zip.output_path
  function_name = "img-pipeline-processor-${var.environment}"
  role          = aws_iam_role.processor_role.arn
  handler       = "processor.handler"
  runtime       = "python3.9"

  source_code_hash = data.archive_file.processor_zip.output_base64sha256

  environment {
    variables = {
      PROCESSED_BUCKET = aws_s3_bucket.processed_bucket.id
      SNS_TOPIC_ARN    = aws_sns_topic.completion_topic.arn
    }
  }
}

resource "aws_lambda_event_source_mapping" "sqs_processor_trigger" {
  event_source_arn = aws_sqs_queue.metadata_queue.arn
  function_name    = aws_lambda_function.processor_lambda.arn
  batch_size       = 10
  enabled          = true
}

resource "aws_s3_bucket_cors_configuration" "upload_cors" {
  bucket = aws_s3_bucket.upload_bucket.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "POST", "GET", "HEAD"]
    allowed_origins = ["*"] 
    expose_headers  = ["ETag", "x-amz-meta-uploader-email"]
    max_age_seconds = 3000
  }
}

resource "aws_api_gateway_method" "upload_url_options" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.upload_url_resource.id
  http_method   = "OPTIONS"
  authorization = "NONE" 
}

resource "aws_api_gateway_integration" "upload_url_options_integration" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.upload_url_resource.id
  http_method = aws_api_gateway_method.upload_url_options.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "options_200" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.upload_url_resource.id
  http_method = aws_api_gateway_method.upload_url_options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "options_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.upload_url_resource.id
  http_method = aws_api_gateway_method.upload_url_options.http_method
  status_code = aws_api_gateway_method_response.options_200.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,x-amz-meta-uploader-email'"
    "method.response.header.Access-Control-Allow-Methods" = "'POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
}

# --- CloudFront & S3 Frontend Hosting ---

resource "aws_s3_bucket" "frontend_bucket" {
  bucket        = "week4-img-pipeline-frontend-${data.aws_caller_identity.current.account_id}-${var.environment}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "frontend_bucket_block" {
  bucket                  = aws_s3_bucket.frontend_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "oac" {
  name                              = "img-pipeline-oac-${var.environment}"
  description                       = "OAC for image pipeline frontend S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend_distribution" {
  origin {
    domain_name              = aws_s3_bucket.frontend_bucket.bucket_regional_domain_name
    origin_id                = "S3-${aws_s3_bucket.frontend_bucket.id}"
    origin_access_control_id = aws_cloudfront_origin_access_control.oac.id
  }

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.frontend_bucket.id}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

resource "aws_s3_bucket_policy" "frontend_policy" {
  bucket = aws_s3_bucket.frontend_bucket.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCloudFrontServicePrincipal"
        Effect    = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.frontend_bucket.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.frontend_distribution.arn
          }
        }
      }
    ]
  })
}

resource "aws_s3_object" "frontend_index" {
  bucket       = aws_s3_bucket.frontend_bucket.id
  key          = "index.html"
  content      = templatefile("${path.module}/index.html.tftpl", {
    user_pool_id  = aws_cognito_user_pool.user_pool.id
    app_client_id = aws_cognito_user_pool_client.user_pool_client.id
    api_url       = "${aws_api_gateway_stage.api_stage.invoke_url}/${aws_api_gateway_resource.upload_url_resource.path_part}"
    aws_region    = var.aws_region
  })
  content_type  = "text/html"
  cache_control = "no-cache, no-store, must-revalidate"
}
