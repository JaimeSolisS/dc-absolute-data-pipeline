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

variable "athena_database_name" {
  description = "Name of the Athena database"
  type        = string
}