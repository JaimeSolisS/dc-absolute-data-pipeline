resource "aws_s3_bucket" "bronze" {
  bucket        = var.s3_bronze_bucket
  force_destroy = true
}

resource "aws_s3_bucket" "silver" {
  bucket        = var.s3_silver_bucket
  force_destroy = true
}

resource "aws_s3_bucket" "gold" {
  bucket        = var.s3_gold_bucket
  force_destroy = true
}

resource "aws_s3_bucket" "control" {
  bucket        = var.s3_control_bucket
  force_destroy = true
}

resource "aws_s3_bucket" "athena_query_results" {
  bucket        = var.athena_query_results_bucket
  force_destroy = true
}
