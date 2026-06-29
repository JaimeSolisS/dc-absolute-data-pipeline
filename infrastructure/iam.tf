# Shared execution role for all Lambda functions in the project
resource "aws_iam_role" "lambda_exec" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Grants CloudWatch Logs access (required for any Lambda)
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Grants read on bronze and write on silver/gold — expand as new Lambdas are added
resource "aws_iam_role_policy" "lambda_s3" {
  name = "${var.project_name}-lambda-s3"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "arn:aws:s3:::${var.s3_bronze_bucket}/*"
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"]
        Resource = [
          "arn:aws:s3:::${var.s3_silver_bucket}",
          "arn:aws:s3:::${var.s3_silver_bucket}/*",
          "arn:aws:s3:::${var.s3_gold_bucket}",
          "arn:aws:s3:::${var.s3_gold_bucket}/*",
          "arn:aws:s3:::${var.s3_bronze_bucket}",
          "arn:aws:s3:::${var.s3_bronze_bucket}/*",
          "arn:aws:s3:::${var.s3_control_bucket}",
          "arn:aws:s3:::${var.s3_control_bucket}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:DeleteObject",
          "s3:GetBucketLocation",
          "s3:AbortMultipartUpload",
          "s3:ListMultipartUploadParts"
        ]
        Resource = [
          "arn:aws:s3:::${var.athena_query_results_bucket}",
          "arn:aws:s3:::${var.athena_query_results_bucket}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = ["glue:GetTable",
          "glue:GetDatabase",
          "glue:CreateTable",
          "glue:UpdateTable",
          "glue:GetPartitions",
          "glue:CreatePartition",
          "glue:BatchCreatePartition",
          "glue:GetCrawler",
          "glue:StartCrawler"]
        Resource = [
          "*"
        ]
      },
      {
        Effect = "Allow"
        Action = ["athena:GetWorkGroup",
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
        "athena:GetQueryResults"]
        Resource = [
          "*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = "*"
      },
    ]
  })
}

# Execution role for the Glue bronze-to-silver job
resource "aws_iam_role" "glue_exec" {
  name = "${var.project_name}-glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "glue.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue_s3" {
  name = "${var.project_name}-glue-s3"
  role = aws_iam_role.glue_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          "arn:aws:s3:::${var.s3_bronze_bucket}",
          "arn:aws:s3:::${var.s3_bronze_bucket}/*",
          "arn:aws:s3:::${var.glue_scripts_bucket}",
          "arn:aws:s3:::${var.glue_scripts_bucket}/*",
        ]
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = [
          "arn:aws:s3:::${var.s3_silver_bucket}",
          "arn:aws:s3:::${var.s3_silver_bucket}/*",
          "arn:aws:s3:::${var.s3_control_bucket}",
          "arn:aws:s3:::${var.s3_control_bucket}/*",
        ]
      },
    ]
  })
}