provider "aws" {
  region = var.aws_region
}

resource "aws_s3_bucket" "feedback_storage_bucket" {
  bucket        = "${var.project_name}-storage-${var.environment}-${random_string.suffix.result}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "block_storage_public" {
  bucket                  = aws_s3_bucket.feedback_storage_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cognito_user_pool" "student_pool" {
  name = "${var.project_name}-pool-${var.environment}"

  username_attributes = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
  }

  lambda_config {
    pre_sign_up = aws_lambda_function.auto_confirm_lambda.arn
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_cognito_user_pool_client" "student_client" {
  name         = "${var.project_name}-client-${var.environment}"
  user_pool_id = aws_cognito_user_pool.student_pool.id
  generate_secret = false
  explicit_auth_flows = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]
}

resource "aws_iam_role" "lambda_exec_role" {
  name = "${var.project_name}-lambda-role-${var.environment}"
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
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_s3_policy" {
    name = "${var.project_name}-s3-policy-${var.environment}"
    role = aws_iam_role.lambda_exec_role.id
    policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
            {
                Effect = "Allow"
                Action = [
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:ListBucket"
                ]
                Resource = [
                    aws_s3_bucket.feedback_storage_bucket.arn,
                    "${aws_s3_bucket.feedback_storage_bucket.arn}/*"
                ]
            }
        ]
    })
}

data "archive_file" "post_zip" {
  type        = "zip"
  source_file = "${path.module}/post_feedback.py"
  output_path = "${path.module}/post_feedback.zip"
}

data "archive_file" "get_zip" {
  type        = "zip"
  source_file = "${path.module}/get_feedback.py"
  output_path = "${path.module}/get_feedback.zip"
}

resource "aws_lambda_function" "post_feedback_lambda" {
  function_name = "${var.project_name}-post-${var.environment}"
  role          = aws_iam_role.lambda_exec_role.arn
  handler       = "post_feedback.lambda_handler"
  runtime       = "python3.11"
  filename      = data.archive_file.post_zip.output_path
  source_code_hash = data.archive_file.post_zip.output_base64sha256

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.feedback_storage_bucket.id
    }
  }
}

resource "aws_lambda_function" "get_feedback_lambda" {
  function_name = "${var.project_name}-get-${var.environment}"
  role          = aws_iam_role.lambda_exec_role.arn
  handler       = "get_feedback.lambda_handler"
  runtime       = "python3.11"
  filename      = data.archive_file.get_zip.output_path
  source_code_hash = data.archive_file.get_zip.output_base64sha256

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.feedback_storage_bucket.id
    }
  }
}

data "archive_file" "auto_confirm_zip" {
  type        = "zip"
  source_file = "${path.module}/auto_confirm.py"
  output_path = "${path.module}/auto_confirm.zip"
}

resource "aws_lambda_function" "auto_confirm_lambda" {
  function_name    = "${var.project_name}-auto-confirm-${var.environment}"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "auto_confirm.lambda_handler"
  runtime          = "python3.11"
  filename         = data.archive_file.auto_confirm_zip.output_path
  source_code_hash = data.archive_file.auto_confirm_zip.output_base64sha256
}

resource "aws_lambda_permission" "allow_cognito_invoke" {
  statement_id  = "AllowCognitoInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auto_confirm_lambda.function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = aws_cognito_user_pool.student_pool.arn
}

resource "aws_api_gateway_rest_api" "feedback_api" {
  name = "${var.project_name}-api-${var.environment}"
}

resource "aws_api_gateway_resource" "feedback_route" {
  rest_api_id = aws_api_gateway_rest_api.feedback_api.id
  parent_id   = aws_api_gateway_rest_api.feedback_api.root_resource_id
  path_part   = "feedback"
}

resource "aws_api_gateway_authorizer" "cognito_auth" {
  name                   = "${var.project_name}-authorizer-${var.environment}"
  rest_api_id            = aws_api_gateway_rest_api.feedback_api.id
  type                    = "COGNITO_USER_POOLS"
  provider_arns           = [aws_cognito_user_pool.student_pool.arn]
}

resource "aws_api_gateway_method" "post_method" {
  rest_api_id   = aws_api_gateway_rest_api.feedback_api.id
  resource_id   = aws_api_gateway_resource.feedback_route.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "post_integration" {
  rest_api_id             = aws_api_gateway_rest_api.feedback_api.id
  resource_id             = aws_api_gateway_resource.feedback_route.id
  http_method             = aws_api_gateway_method.post_method.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.post_feedback_lambda.invoke_arn
}

resource "aws_api_gateway_method" "get_method" {
  rest_api_id   = aws_api_gateway_rest_api.feedback_api.id
  resource_id   = aws_api_gateway_resource.feedback_route.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "get_integration" {
  rest_api_id             = aws_api_gateway_rest_api.feedback_api.id
  resource_id             = aws_api_gateway_resource.feedback_route.id
  http_method             = aws_api_gateway_method.get_method.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.get_feedback_lambda.invoke_arn
}

resource "aws_lambda_permission" "apigw_allow_post" {
  statement_id  = "AllowPostExecutionFromAPIGatewayPost"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.post_feedback_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.feedback_api.execution_arn}/*/*/feedback"
}

resource "aws_lambda_permission" "apigw_allow_get" {
  statement_id  = "AllowGetExecutionFromAPIGatewayGet"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_feedback_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.feedback_api.execution_arn}/*/*/feedback"
}
# Download nested route under /feedback
resource "aws_api_gateway_resource" "download_route" {
  rest_api_id = aws_api_gateway_rest_api.feedback_api.id
  parent_id   = aws_api_gateway_resource.feedback_route.id
  path_part   = "download"
}

resource "aws_api_gateway_method" "download_get_method" {
  rest_api_id   = aws_api_gateway_rest_api.feedback_api.id
  resource_id   = aws_api_gateway_resource.download_route.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito_auth.id
}

resource "aws_api_gateway_integration" "download_get_integration" {
  rest_api_id             = aws_api_gateway_rest_api.feedback_api.id
  resource_id             = aws_api_gateway_resource.download_route.id
  http_method             = aws_api_gateway_method.download_get_method.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.get_feedback_lambda.invoke_arn
}

resource "aws_lambda_permission" "apigw_allow_download" {
  statement_id  = "AllowDownloadExecutionFromAPIGatewayGet"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_feedback_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.feedback_api.execution_arn}/*/*/feedback/download"
}

resource "aws_api_gateway_method" "download_cors_options" {
  rest_api_id   = aws_api_gateway_rest_api.feedback_api.id
  resource_id   = aws_api_gateway_resource.download_route.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "download_cors_integration" {
  rest_api_id = aws_api_gateway_rest_api.feedback_api.id
  resource_id = aws_api_gateway_resource.download_route.id
  http_method = aws_api_gateway_method.download_cors_options.http_method
  type        = "MOCK"
  
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "download_cors_response" {
  rest_api_id = aws_api_gateway_rest_api.feedback_api.id
  resource_id = aws_api_gateway_resource.download_route.id
  http_method = aws_api_gateway_method.download_cors_options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true,
    "method.response.header.Access-Control-Allow-Methods" = true,
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "download_cors_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.feedback_api.id
  resource_id = aws_api_gateway_resource.download_route.id
  http_method = aws_api_gateway_method.download_cors_options.http_method
  status_code = aws_api_gateway_method_response.download_cors_response.status_code
  
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'",
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }

  depends_on = [aws_api_gateway_integration.download_cors_integration]
}

resource "aws_api_gateway_method" "cors_options" {
  rest_api_id   = aws_api_gateway_rest_api.feedback_api.id
  resource_id   = aws_api_gateway_resource.feedback_route.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "cors_integration" {
  rest_api_id = aws_api_gateway_rest_api.feedback_api.id
  resource_id = aws_api_gateway_resource.feedback_route.id
  http_method = aws_api_gateway_method.cors_options.http_method
  type        = "MOCK"
  
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "cors_response" {
  rest_api_id = aws_api_gateway_rest_api.feedback_api.id
  resource_id = aws_api_gateway_resource.feedback_route.id
  http_method = aws_api_gateway_method.cors_options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true,
    "method.response.header.Access-Control-Allow-Methods" = true,
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "cors_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.feedback_api.id
  resource_id = aws_api_gateway_resource.feedback_route.id
  http_method = aws_api_gateway_method.cors_options.http_method
  status_code = aws_api_gateway_method_response.cors_response.status_code
  
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS,POST'",
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }

  depends_on = [aws_api_gateway_integration.cors_integration]
}

resource "aws_api_gateway_gateway_response" "unauthorized_cors" {
  rest_api_id   = aws_api_gateway_rest_api.feedback_api.id
  response_type = "UNAUTHORIZED"

  response_templates = {
    "application/json" = "{\"message\":$context.error.messageString}"
  }

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
    "gatewayresponse.header.Access-Control-Allow-Methods" = "'GET,OPTIONS,POST'"
  }
}

resource "aws_api_gateway_gateway_response" "access_denied_cors" {
  rest_api_id   = aws_api_gateway_rest_api.feedback_api.id
  response_type = "ACCESS_DENIED"

  response_templates = {
    "application/json" = "{\"message\":$context.error.messageString}"
  }

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
    "gatewayresponse.header.Access-Control-Allow-Methods" = "'GET,OPTIONS,POST'"
  }
}

resource "aws_api_gateway_deployment" "api_deploy" {
  depends_on = [
    aws_api_gateway_integration.post_integration,
    aws_api_gateway_integration.get_integration,
    aws_api_gateway_integration_response.cors_integration_response,
    aws_api_gateway_integration.download_get_integration,
    aws_api_gateway_integration_response.download_cors_integration_response
  ]
  rest_api_id = aws_api_gateway_rest_api.feedback_api.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.feedback_route.id,
      aws_api_gateway_method.post_method.id,
      aws_api_gateway_integration.post_integration.id,
      aws_api_gateway_method.get_method.id,
      aws_api_gateway_integration.get_integration.id,
      aws_api_gateway_authorizer.cognito_auth.id,
      aws_api_gateway_integration_response.cors_integration_response.id,
      aws_api_gateway_resource.download_route.id,
      aws_api_gateway_method.download_get_method.id,
      aws_api_gateway_integration.download_get_integration.id,
      aws_api_gateway_integration_response.download_cors_integration_response.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "api_stage" {
  deployment_id = aws_api_gateway_deployment.api_deploy.id
  rest_api_id = aws_api_gateway_rest_api.feedback_api.id
  stage_name = var.environment
}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "aws_s3_bucket" "frontend_bucket" {
  bucket = "${var.project_name}-frontend-${var.environment}-${random_string.suffix.result}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "block_public" {
  bucket = aws_s3_bucket.frontend_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "index_html" {
    bucket = aws_s3_bucket.frontend_bucket.id
    key    = "index.html"
    source = "${path.module}/index.html"
    content_type = "text/html"
    etag = filemd5("${path.module}/index.html")
}

resource "aws_s3_object" "app_js" {
    bucket = aws_s3_bucket.frontend_bucket.id
    key    = "app.js"
    source = "${path.module}/app.js"
    content_type = "application/javascript"
    etag = filemd5("${path.module}/app.js")
}

resource "aws_s3_object" "favicon" {
  bucket       = aws_s3_bucket.frontend_bucket.id
  key          = "favicon.ico"
  source       = "${path.module}/favicon.ico"
  content_type = "image/x-icon"
  etag         = filemd5("${path.module}/favicon.ico")
}

resource "aws_cloudfront_origin_access_control" "oac" {
    name = "${var.project_name}-oac-${var.environment}"
    description = "OAC for CloudFront to securely access S3 bucket"
    origin_access_control_origin_type = "s3"
    signing_behavior = "always"
    signing_protocol = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend_cdn" {
    origin {
        domain_name = aws_s3_bucket.frontend_bucket.bucket_regional_domain_name
        origin_id   = "S3-${aws_s3_bucket.frontend_bucket.id}"
        origin_access_control_id = aws_cloudfront_origin_access_control.oac.id
    }

    enabled             = true
    is_ipv6_enabled     = true
    default_root_object = "index.html"

    default_cache_behavior {
        target_origin_id       = "S3-${aws_s3_bucket.frontend_bucket.id}"
        allowed_methods        = ["GET", "HEAD", "OPTIONS"]
        cached_methods         = ["GET", "HEAD"]
        
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
}

resource "aws_s3_bucket_policy" "frontend_policy" {
    bucket = aws_s3_bucket.frontend_bucket.id
    policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
            {
                Effect = "Allow"
                Principal = {
                    Service = "cloudfront.amazonaws.com"
                }
                Action = "s3:GetObject"
                Resource = "${aws_s3_bucket.frontend_bucket.arn}/*"
                Condition = {
                    StringEquals = {
                        "AWS:SourceArn" = aws_cloudfront_distribution.frontend_cdn.arn
                    }
                }
            }
        ]
    })
}

resource "aws_s3_object" "config_js" {
    bucket       = aws_s3_bucket.frontend_bucket.id
    key          = "config.js"
    content_type = "application/javascript"
    content      = <<EOF
window.API_CONFIG = {
  API_URL: "${aws_api_gateway_stage.api_stage.invoke_url}/feedback",
  CLIENT_ID: "${aws_cognito_user_pool_client.student_client.id}",
  REGION: "${var.aws_region}",
  ADMIN_SECRET_HASH: "${sha256(var.admin_secret_key)}"
};
EOF
}