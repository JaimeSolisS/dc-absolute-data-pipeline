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

resource "aws_s3_bucket" "glue_scripts" {
  bucket        = var.glue_scripts_bucket
  force_destroy = true
}

resource "aws_s3_bucket" "assets" {
  bucket        = var.s3_assets_bucket
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "assets" {
  bucket = aws_s3_bucket.assets.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "assets_public_read" {
  bucket     = aws_s3_bucket.assets.id
  depends_on = [aws_s3_bucket_public_access_block.assets]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "arn:aws:s3:::${var.s3_assets_bucket}/*"
    }]
  })
}

resource "aws_s3_object" "banners" {
  for_each = toset([
    "banner.png", "banner2.png", "banner3.png",
    "banner4.png", "banner5.png", "banner6.png"
  ])

  bucket       = aws_s3_bucket.assets.id
  key          = "banners/${each.key}"
  source       = "${path.module}/../img/${each.key}"
  source_hash  = filemd5("${path.module}/../img/${each.key}")
  content_type = "image/png"
}
