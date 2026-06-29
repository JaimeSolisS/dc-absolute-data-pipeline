variable "project_name" {
  description = "Project name used as a prefix for shared resources"
  type        = string
}

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "api_key" {
  description = "API key for external data source"
  type        = string
  sensitive   = true
}

variable "s3_bronze_bucket" {
  description = "S3 bucket for raw ingested data (bronze layer)"
  type        = string
}

variable "s3_silver_bucket" {
  description = "S3 bucket for cleaned/transformed data (silver layer)"
  type        = string
}

variable "s3_gold_bucket" {
  description = "S3 bucket for rag-ready data (gold layer)"
  type        = string
}

variable "s3_control_bucket" {
  description = "S3 bucket for control data"
  type        = string
}

variable "athena_query_results_bucket" {
  description = "S3 bucket for Athena query results"
  type        = string
}

variable "glue_scripts_bucket" {
  description = "S3 bucket for Glue scripts"
  type        = string
}


variable "aws_wrangler_layer_arn" {
  description = "ARN of the AWS SDK for Pandas (awswrangler) Lambda layer."
  type        = string
}


variable "lambda_function_name_fetch_volumes" {
    description = "Name of the Lambda function that fetches volume data"
    type        = string
}

variable "lambda_function_name_detect_changed_volumes" {
    description = "Name of the Lambda function that detects changed volume data"
    type        = string
}

variable "lambda_function_name_fetch_issues_for_changed_volumes" {
    description = "Name of the Lambda function that fetches issues for changed volume data"
    type        = string
}

variable "lambda_function_name_detect_changed_issues" {
    description = "Name of the Lambda function that detects changed issue data"
    type        = string
}

variable "lambda_function_name_fetch_changed_issues_details" {
    description = "Name of the Lambda function that fetches details for changed issue data"
    type        = string
}

variable "athena_database_name" {
  description = "Name of the Athena database"
  type        = string
}

variable "step_function_name" {
  description = "Name of the Step Functions state machine for the ingestion pipeline"
  type        = string
}

variable "glue_job_name" {
  description = "Name of the Glue job that transforms bronze data to silver Iceberg tables"
  type        = string
}

variable "glue_warehouse_path" {
  description = "S3 path used as the Iceberg warehouse root (e.g. s3://bucket/warehouse/)"
  type        = string
}

variable "lambda_function_name_send_pipeline_notification" {
  description = "Name of the Lambda function that sends the SES pipeline notification"
  type        = string
}

variable "ses_sender_email" {
  description = "Verified SES email address used as the notification sender"
  type        = string
}

variable "ses_recipient_email" {
  description = "Email address that receives the pipeline run notification"
  type        = string
}