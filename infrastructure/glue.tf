resource "aws_glue_catalog_database" "absolute" {
  name = var.athena_database_name
}

resource "aws_glue_catalog_table" "control_volume_state" {
  database_name = aws_glue_catalog_database.absolute.name
  name          = "control_volume_state"

  table_type = "EXTERNAL_TABLE"

  open_table_format_input {
    iceberg_input {
      metadata_operation = "CREATE"
      version            = "2"
    }
  }

  storage_descriptor {
    location      = "s3://dc-absolute-data-pipeline-control/volume_state/"
    input_format  = "org.apache.hadoop.mapred.FileInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "volume_id"
      type = "bigint"
    }
    columns {
      name = "name"
      type = "string"
    }
    columns {
      name = "date_last_updated"
      type = "timestamp"
    }
    columns {
      name = "count_of_issues"
      type = "int"
    }
    columns {
      name = "last_issue_id"
      type = "bigint"
    }
    columns {
      name = "last_checked_at"
      type = "timestamp"
    }
    columns {
      name = "run_id"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "control_issue_state" {
  database_name = aws_glue_catalog_database.absolute.name
  name          = "control_issue_state"

  table_type = "EXTERNAL_TABLE"

  open_table_format_input {
    iceberg_input {
      metadata_operation = "CREATE"
      version            = "2"
    }
  }

  storage_descriptor {
    location      = "s3://dc-absolute-data-pipeline-control/issue_state/"
    input_format  = "org.apache.hadoop.mapred.FileInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "issue_id"
      type = "bigint"
    }
    columns {
      name = "volume_id"
      type = "bigint"
    }

    columns {
      name = "name"
      type = "string"
    }

    columns {
      name = "issue_number"
      type = "string"
    }
    columns {
      name = "date_last_updated"
      type = "timestamp"
    }
    columns {
      name = "detail_fetched_at"
      type = "timestamp"
    }
    columns {
      name = "content_hash"
      type = "string"
    }
    columns {
      name = "run_id"
      type = "string"
    }
  }
}

# Upload Glue job script to S3; re-uploads automatically when the file changes
resource "aws_s3_object" "glue_job_script" {
  bucket       = aws_s3_bucket.glue_scripts.bucket
  key          = "glue_jobs/bronze_to_silver.py"
  source       = "${path.module}/glue_jobs/bronze_to_silver.py"
  source_hash  = filemd5("${path.module}/glue_jobs/bronze_to_silver.py")
  content_type = "text/x-python"
}

resource "aws_glue_job" "bronze_to_silver" {
  name     = var.glue_job_name
  role_arn = aws_iam_role.glue_exec.arn

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  
  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_object.glue_job_script.bucket}/${aws_s3_object.glue_job_script.key}"
    python_version  = "3"
  }

  # Static args baked into the job; run-specific args (keys, run_id) come from Step Functions
  default_arguments = {
    "--enable-glue-datacatalog" = "true"
    "--datalake-formats"        = "iceberg"
    "--bronze_bucket"           = var.s3_bronze_bucket
    "--database"                = var.athena_database_name
    "--warehouse_path"          = var.glue_warehouse_path
  }
}