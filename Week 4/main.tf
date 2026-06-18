provider "aws" {
    region = var.aws_region
}

resource "aws_cognito_user_pool" "user_pool" {
    name = "${var.user_pool_name}-${var.environment}"

    username_attributes = ["email"]
    auto_verified_attributes = ["email"]

    password_policy {
        minimum_length = 8
        require_lowercase = true
        require_numbers = true
        require_symbols = true
        require_uppercase = true
    }

    verification_message_template {
        email_subject = "Verify your email"
        email_message = "Hello, click on the link to verify your email: {####}"
        default_email_option = "CONFIRM_WITH_CODE"
    }
}

resource "aws_cognito_user_pool_client" "user_pool_client" {
    name = "${var.app_client_name}-${var.environment}"
    user_pool_id = aws_cognito_user_pool.user_pool.id
    
    generate_secret = false

    explicit_auth_flows = [
        "ALLOW_USER_PASSWORD_AUTH",
        "ALLOW_USER_SRP_AUTH",
        "ALLOW_REFRESH_TOKEN_AUTH"
    ]
}

resource "aws_api_gateway_rest_api" "api" {
  name        = "week4-api-${var.environment}"
  description = "Protected API Gateway for Week 4 Labs"
}

resource "aws_api_gateway_authorizer" "cognito_authorizer" {
  name          = "cognito-authorizer"
  type          = "COGNITO_USER_POOLS"
  rest_api_id   = aws_api_gateway_rest_api.api.id
  provider_arns = [aws_cognito_user_pool.user_pool.arn]
}

resource "aws_api_gateway_resource" "secure_resource" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_rest_api.api.root_resource_id
  path_part   = "secure"
}

resource "aws_api_gateway_method" "secure_method" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.secure_resource.id
  http_method   = "POST"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito_authorizer.id
}

resource "aws_api_gateway_integration" "api_integration" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.secure_resource.id
  http_method             = aws_api_gateway_method.secure_method.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.producer_lambda.invoke_arn
}

resource "aws_lambda_permission" "apigw_lambda" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.producer_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*"
}

resource "aws_iam_role" "producer_role" {
  name = "week4-producer-role-${var.environment}"

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

resource "aws_iam_role_policy_attachment" "producer_logs" {
  role       = aws_iam_role.producer_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "producer_sqs_policy" {
  name        = "week4-producer-sqs-${var.environment}"
  description = "Allow Producer Lambda to send messages to SQS"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.queue.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "producer_sqs" {
  role       = aws_iam_role.producer_role.name
  policy_arn = aws_iam_policy.producer_sqs_policy.arn
}

data "archive_file" "producer_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/producer.py"
  output_path = "${path.module}/producer.zip"
}

resource "aws_lambda_function" "producer_lambda" {
  filename      = data.archive_file.producer_zip.output_path
  function_name = "week4-producer-${var.environment}"
  role          = aws_iam_role.producer_role.arn
  handler       = "producer.handler"
  runtime       = "python3.9"

  source_code_hash = data.archive_file.producer_zip.output_base64sha256

  environment {
    variables = {
      QUEUE_URL = aws_sqs_queue.queue.url
    }
  }
}

resource "aws_api_gateway_deployment" "api_deployment" {
  depends_on = [
    aws_api_gateway_integration.api_integration
  ]
  rest_api_id = aws_api_gateway_rest_api.api.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.secure_resource.id,
      aws_api_gateway_method.secure_method.id,
      aws_api_gateway_integration.api_integration.id
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

resource "aws_sns_topic" "sns_topic" {
    name = "week4-notifications-${var.environment}"
}

resource "aws_sns_topic_subscription" "email_subscription" {
    topic_arn = aws_sns_topic.sns_topic.arn
    protocol = "email"
    endpoint = var.sns_subscription_email

    lifecycle {
        ignore_changes = [
            endpoint,
            protocol,
            topic_arn
        ]
    }
}

resource "aws_sqs_queue" "queue" {
  name                      = "week4-queue-${var.environment}"
  delay_seconds             = 0
  max_message_size          = 262144
  message_retention_seconds = 86400
  receive_wait_time_seconds = 10 
}

resource "aws_iam_role" "lambda_role" {
  name = "week4-lambda-execution-role-${var.environment}"

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

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_sqs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole"
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/index.py"
  output_path = "${path.module}/lambda.zip"
}

resource "aws_lambda_function" "sqs_lambda" {
  filename      = data.archive_file.lambda_zip.output_path
  function_name = "week4-sqs-processor-${var.environment}"
  role          = aws_iam_role.lambda_role.arn
  handler       = "index.handler"
  runtime       = "python3.9"

  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      SNS_TOPIC_ARN = aws_sns_topic.sns_topic.arn
    }
  }
}

resource "aws_iam_policy" "lambda_sns_policy" {
  name        = "week4-lambda-sns-${var.environment}"
  description = "Allow Consumer Lambda to publish to SNS"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = aws_sns_topic.sns_topic.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_sns" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_sns_policy.arn
}

resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.queue.arn
  function_name    = aws_lambda_function.sqs_lambda.arn
  batch_size       = 10
  enabled          = true
}
