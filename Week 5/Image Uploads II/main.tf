provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}


resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = {
    Name = "img-pipeline-vpc-${var.environment}"
  }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
  tags = {
    Name = "img-pipeline-igw-${var.environment}"
  }
}

resource "aws_subnet" "public_1" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]
  tags = {
    Name = "img-pipeline-public-1-${var.environment}"
  }
}

resource "aws_subnet" "public_2" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = data.aws_availability_zones.available.names[1]
  tags = {
    Name = "img-pipeline-public-2-${var.environment}"
  }
}

resource "aws_subnet" "private_1" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.3.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]
  tags = {
    Name = "img-pipeline-private-1-${var.environment}"
  }
}

resource "aws_subnet" "private_2" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.4.0/24"
  availability_zone = data.aws_availability_zones.available.names[1]
  tags = {
    Name = "img-pipeline-private-2-${var.environment}"
  }
}

resource "aws_eip" "nat_eip" {
  domain     = "vpc"
  depends_on = [aws_internet_gateway.igw]
}

resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat_eip.id
  subnet_id     = aws_subnet.public_1.id
  tags = {
    Name = "img-pipeline-nat-${var.environment}"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = {
    Name = "img-pipeline-public-rt-${var.environment}"
  }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat.id
  }
  tags = {
    Name = "img-pipeline-private-rt-${var.environment}"
  }
}

resource "aws_route_table_association" "public_1" {
  subnet_id      = aws_subnet.public_1.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_2" {
  subnet_id      = aws_subnet.public_2.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private_1" {
  subnet_id      = aws_subnet.private_1.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "private_2" {
  subnet_id      = aws_subnet.private_2.id
  route_table_id = aws_route_table.private.id
}



resource "aws_security_group" "lambda_sg" {
  name        = "img-pipeline-lambda-sg-${var.environment}"
  description = "Allows Lambdas to send outbound traffic"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "img-pipeline-lambda-sg"
  }
}

resource "aws_security_group" "rds_proxy_sg" {
  name        = "img-pipeline-rds-proxy-sg-${var.environment}"
  description = "Allows Lambdas to connect to RDS Proxy"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "img-pipeline-rds-proxy-sg"
  }
}

resource "aws_security_group" "db_sg" {
  name        = "img-pipeline-db-sg-${var.environment}"
  description = "Allows traffic from RDS Proxy and Lambda security groups"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.rds_proxy_sg.id, aws_security_group.lambda_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "img-pipeline-db-sg"
  }
}

resource "aws_security_group" "redis_sg" {
  name        = "img-pipeline-redis-sg-${var.environment}"
  description = "Allows traffic from Lambda security groups"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "img-pipeline-redis-sg"
  }
}



resource "random_password" "db_password" {
  length  = 16
  special = false
}

resource "aws_db_subnet_group" "db_subnet" {
  name       = "img-pipeline-db-subnets-${var.environment}"
  subnet_ids = [aws_subnet.private_1.id, aws_subnet.private_2.id]
}

resource "aws_db_instance" "db" {
  identifier             = "img-pipeline-db-${var.environment}"
  allocated_storage      = 20
  engine                 = "mysql"
  engine_version         = "8.0"
  instance_class         = "db.t4g.micro"
  db_name                = "image_pipeline"
  username               = "admin"
  password               = random_password.db_password.result
  db_subnet_group_name   = aws_db_subnet_group.db_subnet.name
  vpc_security_group_ids = [aws_security_group.db_sg.id]
  skip_final_snapshot    = true
}

resource "aws_secretsmanager_secret" "db_secret" {
  name_prefix             = "img-pipeline-db-secret-${var.environment}"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "db_secret_ver" {
  secret_id = aws_secretsmanager_secret.db_secret.id
  secret_string = jsonencode({
    username             = "admin"
    password             = random_password.db_password.result
    engine               = "mysql"
    host                 = aws_db_instance.db.address
    port                 = 3306
    dbInstanceIdentifier = aws_db_instance.db.id
  })
}

resource "aws_iam_role" "rds_proxy_role" {
  name = "img-pipeline-rds-proxy-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "rds.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "rds_proxy_secrets_policy" {
  name        = "img-pipeline-rds-proxy-secrets-${var.environment}"
  description = "Allows RDS Proxy to read Secrets Manager db secret"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = aws_secretsmanager_secret.db_secret.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "rds_proxy_secrets" {
  role       = aws_iam_role.rds_proxy_role.name
  policy_arn = aws_iam_policy.rds_proxy_secrets_policy.arn
}

resource "aws_db_proxy" "db_proxy" {
  name                   = "img-pipeline-db-proxy-${var.environment}"
  debug_logging          = false
  engine_family          = "MYSQL"
  idle_client_timeout    = 1800
  require_tls            = false
  role_arn               = aws_iam_role.rds_proxy_role.arn
  vpc_security_group_ids = [aws_security_group.rds_proxy_sg.id]
  vpc_subnet_ids         = [aws_subnet.private_1.id, aws_subnet.private_2.id]

  auth {
    auth_scheme = "SECRETS"
    description = "Database credentials"
    iam_auth    = "DISABLED"
    secret_arn  = aws_secretsmanager_secret.db_secret.arn
  }
}

resource "aws_db_proxy_default_target_group" "db_proxy_tg" {
  db_proxy_name = aws_db_proxy.db_proxy.name

  connection_pool_config {
    max_connections_percent      = 90
    max_idle_connections_percent = 50
  }
}

resource "aws_db_proxy_target" "db_proxy_target" {
  db_proxy_name          = aws_db_proxy.db_proxy.name
  target_group_name      = aws_db_proxy_default_target_group.db_proxy_tg.name
  db_instance_identifier = aws_db_instance.db.identifier
}



resource "aws_elasticache_subnet_group" "redis_subnet" {
  name       = "img-pipeline-redis-subnets-${var.environment}"
  subnet_ids = [aws_subnet.private_1.id, aws_subnet.private_2.id]
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "img-pipeline-redis-${var.environment}"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.redis_subnet.name
  security_group_ids   = [aws_security_group.redis_sg.id]
}



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

resource "aws_sqs_queue" "metadata_queue" {
  name                      = "img-pipeline-metadata-queue-${var.environment}"
  delay_seconds             = 0
  max_message_size          = 262144
  message_retention_seconds = 86400
  receive_wait_time_seconds = 10
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

  read_attributes  = ["email", "email_verified", "custom:role"]
  write_attributes = ["email", "custom:role"]
}



resource "null_resource" "install_layer_dependencies" {
  triggers = {
    requirements = filesha256("${path.module}/lambda/requirements.txt")
  }
  provisioner "local-exec" {
    command = "pip install -r ${path.module}/lambda/requirements.txt -t ${path.module}/lambda/common_layer/python --only-binary=:all: --platform manylinux2014_x86_64 --upgrade"
  }
}

data "archive_file" "layer_zip" {
  depends_on  = [null_resource.install_layer_dependencies]
  type        = "zip"
  source_dir  = "${path.module}/lambda/common_layer"
  output_path = "${path.module}/common_layer.zip"
}

resource "aws_lambda_layer_version" "common_layer" {
  filename            = data.archive_file.layer_zip.output_path
  layer_name          = "common_dependencies_layer_${var.environment}"
  compatible_runtimes = ["python3.11"]
  source_code_hash    = data.archive_file.layer_zip.output_base64sha256
}



resource "aws_iam_role" "lambda_vpc_role" {
  name = "img-pipeline-lambda-vpc-role-${var.environment}"

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

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_vpc_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_vpc_access" {
  role       = aws_iam_role.lambda_vpc_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_policy" "lambda_aws_permissions" {
  name        = "img-pipeline-lambda-aws-permissions-${var.environment}"
  description = "Allows Lambdas to access S3, SQS, SNS, and Rekognition"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = ["${aws_s3_bucket.upload_bucket.arn}/*", "${aws_s3_bucket.processed_bucket.arn}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["rekognition:DetectLabels"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = aws_sqs_queue.metadata_queue.arn
      },
      {
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = aws_sns_topic.completion_topic.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_permissions_attach" {
  role       = aws_iam_role.lambda_vpc_role.name
  policy_arn = aws_iam_policy.lambda_aws_permissions.arn
}


data "archive_file" "presigned_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/presigned.py"
  output_path = "${path.module}/presigned.zip"
}

resource "aws_lambda_function" "presigned_lambda" {
  filename         = data.archive_file.presigned_zip.output_path
  function_name    = "img-pipeline-presigned-gen-${var.environment}"
  role             = aws_iam_role.lambda_vpc_role.arn
  handler          = "presigned.handler"
  runtime          = "python3.11"
  layers           = [aws_lambda_layer_version.common_layer.arn]
  source_code_hash = data.archive_file.presigned_zip.output_base64sha256
  timeout          = 30

  vpc_config {
    subnet_ids         = [aws_subnet.private_1.id, aws_subnet.private_2.id]
    security_group_ids = [aws_security_group.lambda_sg.id]
  }

  environment {
    variables = {
      UPLOAD_BUCKET = aws_s3_bucket.upload_bucket.id
      DB_HOST       = aws_db_proxy.db_proxy.endpoint
      DB_USER       = "admin"
      DB_PASSWORD   = random_password.db_password.result
      DB_NAME       = "image_pipeline"
      REDIS_HOST    = aws_elasticache_cluster.redis.cache_nodes[0].address
    }
  }
}

data "archive_file" "extractor_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/extractor.py"
  output_path = "${path.module}/extractor.zip"
}

resource "aws_lambda_function" "extractor_lambda" {
  filename         = data.archive_file.extractor_zip.output_path
  function_name    = "img-pipeline-extractor-${var.environment}"
  role             = aws_iam_role.lambda_vpc_role.arn
  handler          = "extractor.handler"
  runtime          = "python3.11"
  layers           = [aws_lambda_layer_version.common_layer.arn]
  source_code_hash = data.archive_file.extractor_zip.output_base64sha256
  timeout          = 30

  vpc_config {
    subnet_ids         = [aws_subnet.private_1.id, aws_subnet.private_2.id]
    security_group_ids = [aws_security_group.lambda_sg.id]
  }

  environment {
    variables = {
      QUEUE_URL   = aws_sqs_queue.metadata_queue.id
      DB_HOST     = aws_db_proxy.db_proxy.endpoint
      DB_USER     = "admin"
      DB_PASSWORD = random_password.db_password.result
      DB_NAME     = "image_pipeline"
      REDIS_HOST  = aws_elasticache_cluster.redis.cache_nodes[0].address
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

data "archive_file" "processor_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/processor.py"
  output_path = "${path.module}/processor.zip"
}

resource "aws_lambda_function" "processor_lambda" {
  filename         = data.archive_file.processor_zip.output_path
  function_name    = "img-pipeline-processor-${var.environment}"
  role             = aws_iam_role.lambda_vpc_role.arn
  handler          = "processor.handler"
  runtime          = "python3.11"
  layers           = [aws_lambda_layer_version.common_layer.arn]
  source_code_hash = data.archive_file.processor_zip.output_base64sha256
  timeout          = 30

  vpc_config {
    subnet_ids         = [aws_subnet.private_1.id, aws_subnet.private_2.id]
    security_group_ids = [aws_security_group.lambda_sg.id]
  }

  environment {
    variables = {
      PROCESSED_BUCKET = aws_s3_bucket.processed_bucket.id
      SNS_TOPIC_ARN    = aws_sns_topic.completion_topic.arn
      DB_HOST          = aws_db_proxy.db_proxy.endpoint
      DB_USER          = "admin"
      DB_PASSWORD      = random_password.db_password.result
      DB_NAME          = "image_pipeline"
      REDIS_HOST       = aws_elasticache_cluster.redis.cache_nodes[0].address
    }
  }
}

resource "aws_lambda_event_source_mapping" "sqs_processor_trigger" {
  event_source_arn = aws_sqs_queue.metadata_queue.arn
  function_name    = aws_lambda_function.processor_lambda.arn
  batch_size       = 10
  enabled          = true
}

data "archive_file" "history_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/history.py"
  output_path = "${path.module}/history.zip"
}

resource "aws_lambda_function" "history_lambda" {
  filename         = data.archive_file.history_zip.output_path
  function_name    = "img-pipeline-history-${var.environment}"
  role             = aws_iam_role.lambda_vpc_role.arn
  handler          = "history.handler"
  runtime          = "python3.11"
  layers           = [aws_lambda_layer_version.common_layer.arn]
  source_code_hash = data.archive_file.history_zip.output_base64sha256
  timeout          = 30

  vpc_config {
    subnet_ids         = [aws_subnet.private_1.id, aws_subnet.private_2.id]
    security_group_ids = [aws_security_group.lambda_sg.id]
  }

  environment {
    variables = {
      DB_HOST     = aws_db_proxy.db_proxy.endpoint
      DB_USER     = "admin"
      DB_PASSWORD = random_password.db_password.result
      DB_NAME     = "image_pipeline"
      REDIS_HOST  = aws_elasticache_cluster.redis.cache_nodes[0].address
    }
  }
}


data "archive_file" "janitor_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/janitor.py"
  output_path = "${path.module}/janitor.zip"
}

resource "aws_lambda_function" "janitor_lambda" {
  filename         = data.archive_file.janitor_zip.output_path
  function_name    = "img-pipeline-janitor-${var.environment}"
  role             = aws_iam_role.lambda_vpc_role.arn
  handler          = "janitor.handler"
  runtime          = "python3.11"
  layers           = [aws_lambda_layer_version.common_layer.arn]
  source_code_hash = data.archive_file.janitor_zip.output_base64sha256
  timeout          = 60

  vpc_config {
    subnet_ids         = [aws_subnet.private_1.id, aws_subnet.private_2.id]
    security_group_ids = [aws_security_group.lambda_sg.id]
  }

  environment {
    variables = {
      UPLOAD_BUCKET = aws_s3_bucket.upload_bucket.id
      QUEUE_URL     = aws_sqs_queue.metadata_queue.id
      DB_HOST       = aws_db_proxy.db_proxy.endpoint
      DB_USER       = "admin"
      DB_PASSWORD   = random_password.db_password.result
      DB_NAME       = "image_pipeline"
      REDIS_HOST    = aws_elasticache_cluster.redis.cache_nodes[0].address
    }
  }
}

resource "aws_cloudwatch_event_rule" "janitor_rule" {
  name                = "img-pipeline-janitor-rule-${var.environment}"
  description         = "Trigger Database Janitor Lambda every 5 minutes"
  schedule_expression = "rate(5 minutes)"
}

resource "aws_cloudwatch_event_target" "janitor_target" {
  rule      = aws_cloudwatch_event_rule.janitor_rule.name
  target_id = "TriggerJanitorLambda"
  arn       = aws_lambda_function.janitor_lambda.arn
}

resource "aws_lambda_permission" "allow_eventbridge_to_janitor" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.janitor_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.janitor_rule.arn
}



resource "aws_api_gateway_rest_api" "api" {
  name        = "img-pipeline-api-${var.environment}"
  description = "Protected API Gateway for Image Processing Pipeline with Caching and RDS"
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

resource "aws_api_gateway_method_response" "upload_url_options_200" {
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

resource "aws_api_gateway_integration_response" "upload_url_options_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.upload_url_resource.id
  http_method = aws_api_gateway_method.upload_url_options.http_method
  status_code = aws_api_gateway_method_response.upload_url_options_200.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,x-amz-meta-uploader-email'"
    "method.response.header.Access-Control-Allow-Methods" = "'POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
}

resource "aws_api_gateway_resource" "history_resource" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_rest_api.api.root_resource_id
  path_part   = "history"
}

resource "aws_api_gateway_method" "history_method" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.history_resource.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito_authorizer.id
}

resource "aws_api_gateway_integration" "history_lambda_integration" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.history_resource.id
  http_method             = aws_api_gateway_method.history_method.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.history_lambda.invoke_arn
}

resource "aws_api_gateway_method" "history_options" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.history_resource.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "history_options_integration" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.history_resource.id
  http_method = aws_api_gateway_method.history_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "history_options_200" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.history_resource.id
  http_method = aws_api_gateway_method.history_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "history_options_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.history_resource.id
  http_method = aws_api_gateway_method.history_options.http_method
  status_code = aws_api_gateway_method_response.history_options_200.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
}

resource "aws_lambda_permission" "apigw_presigned_lambda" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.presigned_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_history_lambda" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.history_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*"
}

resource "aws_api_gateway_deployment" "api_deployment" {
  depends_on = [
    aws_api_gateway_integration.presigned_lambda_integration,
    aws_api_gateway_integration.history_lambda_integration,
    aws_api_gateway_integration_response.upload_url_options_integration_response,
    aws_api_gateway_integration_response.history_options_integration_response
  ]
  rest_api_id = aws_api_gateway_rest_api.api.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.upload_url_resource.id,
      aws_api_gateway_method.upload_url_method.id,
      aws_api_gateway_integration.presigned_lambda_integration.id,
      aws_api_gateway_method.upload_url_options.id,
      aws_api_gateway_integration.upload_url_options_integration.id,
      aws_api_gateway_resource.history_resource.id,
      aws_api_gateway_method.history_method.id,
      aws_api_gateway_integration.history_lambda_integration.id,
      aws_api_gateway_method.history_options.id,
      aws_api_gateway_integration.history_options_integration.id
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



resource "aws_s3_bucket_cors_configuration" "upload_cors" {
  bucket = aws_s3_bucket.upload_bucket.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "POST", "GET", "HEAD"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag", "x-amz-meta-uploader-email", "x-amz-meta-uploader-sub", "x-amz-meta-image-id"]
    max_age_seconds = 3000
  }
}

resource "aws_s3_bucket" "frontend_bucket" {
  bucket        = "week5-img-pipeline-frontend-${data.aws_caller_identity.current.account_id}-${var.environment}"
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
