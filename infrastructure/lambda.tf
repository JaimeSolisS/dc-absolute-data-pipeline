
# Zips the Lambda source folder (including installed dependencies) for deployment
data "archive_file" "fetch_volumes" {
  type        = "zip"
  source_dir  = "${path.module}/lambdas/fetch_volumes"
  output_path = "${path.module}/lambdas/zips/fetch_volumes.zip"
}

# Lambda function — awswrangler and pandas are provided via the managed layer
resource "aws_lambda_function" "fetch_volumes" {
  function_name    = var.lambda_function_name_fetch_volumes
  role             = aws_iam_role.lambda_exec.arn # shared role defined in iam.tf
  runtime          = "python3.11"
  handler          = "lambda_function.lambda_handler"
  timeout          = 300
  memory_size      = 512
  filename         = data.archive_file.fetch_volumes.output_path
  source_code_hash = data.archive_file.fetch_volumes.output_base64sha256
  
  layers = [var.aws_wrangler_layer_arn]

  environment {
    variables = {
      API_KEY    = var.api_key
      BUCKET_BRONZE = var.s3_bronze_bucket
    }
  }
}

data "archive_file" "detect_changed_volumes" {
  type        = "zip"
  source_dir  = "${path.module}/lambdas/detect_changed_volumes"
  output_path = "${path.module}/lambdas/zips/detect_changed_volumes.zip"
}

# Lambda function — awswrangler and pandas are provided via the managed layer
resource "aws_lambda_function" "detect_changed_volumes" {
  function_name    = var.lambda_function_name_detect_changed_volumes
  role             = aws_iam_role.lambda_exec.arn # shared role defined in iam.tf
  runtime          = "python3.11"
  handler          = "lambda_function.lambda_handler"
  timeout          = 300
  memory_size      = 512
  filename         = data.archive_file.detect_changed_volumes.output_path
  source_code_hash = data.archive_file.detect_changed_volumes.output_base64sha256
  
  layers = [var.aws_wrangler_layer_arn]

  environment {
    variables = {
      BRONZE_BUCKET = var.s3_bronze_bucket
      ATHENA_DATABASE = var.athena_database_name
      CONTROL_VOLUME_TABLE = aws_glue_catalog_table.control_volume_state.name
      ATHENA_OUTPUT = var.athena_query_results_bucket
    }
  }
}

data "archive_file" "fetch_issues_for_changed_volumes" {
  type        = "zip"
  source_dir  = "${path.module}/lambdas/fetch_issues_for_changed_volumes"
  output_path = "${path.module}/lambdas/zips/fetch_issues_for_changed_volumes.zip"
}

# Lambda function — awswrangler and pandas are provided via the managed layer
resource "aws_lambda_function" "fetch_issues_for_changed_volumes" {
  function_name    = var.lambda_function_name_fetch_issues_for_changed_volumes
  role             = aws_iam_role.lambda_exec.arn # shared role defined in iam.tf
  runtime          = "python3.11"
  handler          = "lambda_function.lambda_handler"
  timeout          = 300
  memory_size      = 512
  filename         = data.archive_file.fetch_issues_for_changed_volumes.output_path
  source_code_hash = data.archive_file.fetch_issues_for_changed_volumes.output_base64sha256
  
  layers = [var.aws_wrangler_layer_arn]

  environment {
    variables = {
      API_KEY    = var.api_key
      BUCKET_BRONZE = var.s3_bronze_bucket
    }
  }
}

data "archive_file" "detect_changed_issues" {
  type        = "zip"
  source_dir  = "${path.module}/lambdas/detect_changed_issues"
  output_path = "${path.module}/lambdas/zips/detect_changed_issues.zip"
}

# Lambda function — awswrangler and pandas are provided via the managed layer
resource "aws_lambda_function" "detect_changed_issues" {
  function_name    = var.lambda_function_name_detect_changed_issues
  role             = aws_iam_role.lambda_exec.arn # shared role defined in iam.tf
  runtime          = "python3.11"
  handler          = "lambda_function.lambda_handler"
  timeout          = 300
  memory_size      = 512
  filename         = data.archive_file.detect_changed_issues.output_path
  source_code_hash = data.archive_file.detect_changed_issues.output_base64sha256
  
  layers = [var.aws_wrangler_layer_arn]

  environment {
    variables = {
      BRONZE_BUCKET = var.s3_bronze_bucket
      ATHENA_DATABASE = var.athena_database_name
      CONTROL_ISSUE_TABLE = aws_glue_catalog_table.control_issue_state.name
      ATHENA_OUTPUT = var.athena_query_results_bucket
    }
  }
}