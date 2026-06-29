# IAM role that allows Step Functions to invoke Lambda
resource "aws_iam_role" "sfn_exec" {
  name = "${var.project_name}-sfn-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "sfn_invoke_lambda" {
  name = "${var.project_name}-sfn-invoke-lambda"
  role = aws_iam_role.sfn_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = "lambda:InvokeFunction"
      Resource = [
        "${aws_lambda_function.fetch_volumes.arn}:*",
        "${aws_lambda_function.detect_changed_volumes.arn}:*",
        "${aws_lambda_function.fetch_issues_for_changed_volumes.arn}:*",
        "${aws_lambda_function.detect_changed_issues.arn}:*",
        "${aws_lambda_function.fetch_changed_issues_details.arn}:*",
        "${aws_lambda_function.send_pipeline_notification.arn}:*",
      ]
    }]
  })
}

resource "aws_iam_role_policy" "sfn_start_glue_job" {
  name = "${var.project_name}-sfn-start-glue-job"
  role = aws_iam_role.sfn_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "glue:StartJobRun",
        "glue:GetJobRun",
        "glue:GetJobRuns",
        "glue:BatchStopJobRun",
      ]
      Resource = "*"
    }]
  })
}

resource "aws_sfn_state_machine" "absolute_data_pipeline" {
  name     = var.step_function_name
  role_arn = aws_iam_role.sfn_exec.arn

  definition = templatefile("${path.module}/state_machines/ingestion.json", {
    fetch_volumes_arn                      = aws_lambda_function.fetch_volumes.arn
    detect_changed_volumes_arn             = aws_lambda_function.detect_changed_volumes.arn
    fetch_issues_for_changed_volumes_arn   = aws_lambda_function.fetch_issues_for_changed_volumes.arn
    detect_changed_issues_arn              = aws_lambda_function.detect_changed_issues.arn
    fetch_changed_issues_details_arn       = aws_lambda_function.fetch_changed_issues_details.arn
    glue_job_name                          = aws_glue_job.bronze_to_silver.name
    send_pipeline_notification_arn         = aws_lambda_function.send_pipeline_notification.arn
  })
}
