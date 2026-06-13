import sys

from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    lit,
    to_timestamp,
    to_date,
    sha2,
    concat_ws,
    expr,
    from_json,
    to_json,
)
from pyspark.sql.types import ArrayType, StructType, StructField, StringType

# Schema used to normalise credit arrays after JSON inference.
# to_json → from_json forces the correct element type whether Spark inferred
# array<struct<...>> (populated) or array<string> (all-empty arrays).
_credit_schema      = ArrayType(StructType([StructField("name", StringType())]))
_person_credit_schema = ArrayType(StructType([
    StructField("name", StringType()),
    StructField("role", StringType()),
]))


args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "run_id",
        "ingestion_date",
        "bronze_bucket",
        "volumes_key",
        "issues_key",
        "issue_details_key",
        "database",
        "warehouse_path"
    ]
)

run_id = args["run_id"]
ingestion_date = args["ingestion_date"]
bronze_bucket = args["bronze_bucket"]
volumes_key = args["volumes_key"]
issues_key = args["issues_key"]
issue_details_key = args["issue_details_key"]
database = args["database"]
warehouse_path = args["warehouse_path"]

volumes_path = f"s3://{bronze_bucket}/{volumes_key}"
issues_path = f"s3://{bronze_bucket}/{issues_key}"
issue_details_path = f"s3://{bronze_bucket}/{issue_details_key}"

spark = (
    SparkSession.builder
    .appName(args["JOB_NAME"])
    .config("spark.sql.catalog.glue_catalog", "org.apache.iceberg.spark.SparkCatalog")
    .config("spark.sql.catalog.glue_catalog.warehouse", warehouse_path)
    .config("spark.sql.catalog.glue_catalog.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog")
    .config("spark.sql.catalog.glue_catalog.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
    .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
    .config("spark.sql.iceberg.handle-timestamp-without-timezone", "true")
    .getOrCreate()
)

spark.sql(f"CREATE DATABASE IF NOT EXISTS glue_catalog.{database}")


# -------------------------
# Create Iceberg tables
# -------------------------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS glue_catalog.{database}.silver_volumes (
    volume_id BIGINT,
    name STRING,
    api_detail_url STRING,
    site_detail_url STRING,
    count_of_issues INT,
    last_issue_id BIGINT,
    date_last_updated TIMESTAMP,
    ingestion_date DATE,
    run_id STRING
)
USING iceberg
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS glue_catalog.{database}.silver_issues (
    issue_id BIGINT,
    volume_id BIGINT,
    volume_name STRING,
    issue_number STRING,
    name STRING,
    cover_date DATE,
    store_date DATE,
    api_detail_url STRING,
    site_detail_url STRING,
    date_added TIMESTAMP,
    date_last_updated TIMESTAMP,
    ingestion_date DATE,
    run_id STRING
)
USING iceberg
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS glue_catalog.{database}.silver_issue_details (
    issue_id BIGINT,
    volume_id BIGINT,
    volume_name STRING,
    issue_number STRING,
    name STRING,
    description STRING,
    image_url STRING,
    characters ARRAY<STRING>,
    objects ARRAY<STRING>,
    writers ARRAY<STRING>,
    artists ARRAY<STRING>,
    colorists ARRAY<STRING>,
    teams ARRAY<STRING>,
    locations ARRAY<STRING>,
    concepts ARRAY<STRING>,
    site_detail_url STRING,
    api_detail_url STRING,
    store_date DATE,
    cover_date DATE,
    date_added TIMESTAMP,
    date_last_updated TIMESTAMP,
    detail_fetched_at TIMESTAMP,
    ingestion_date DATE,
    run_id STRING,
    content_hash STRING
)
USING iceberg
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS glue_catalog.{database}.control_volume_state (
    volume_id BIGINT,
    name STRING,
    date_last_updated TIMESTAMP,
    count_of_issues INT,
    last_issue_id BIGINT,
    last_checked_at TIMESTAMP,
    run_id STRING
)
USING iceberg
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS glue_catalog.{database}.control_issue_state (
    issue_id BIGINT,
    volume_id BIGINT,
    name STRING,
    issue_number STRING,
    date_last_updated TIMESTAMP,
    detail_fetched_at TIMESTAMP,
    content_hash STRING,
    run_id STRING
)
USING iceberg
""")


# -------------------------
# Volumes
# -------------------------

# File structure: {"volumes": [{volume_id, name, api_detail_url, site_detail_url,
#                               date_last_updated, count_of_issues, last_issue_id}]}
raw_volumes_df = spark.read.option("multiline", "true").json(volumes_path)

volumes_df = raw_volumes_df.selectExpr("explode(volumes) as v").select(
    col("v.volume_id").cast("bigint").alias("volume_id"),
    col("v.name"),
    col("v.api_detail_url"),
    col("v.site_detail_url"),
    col("v.count_of_issues").cast("int").alias("count_of_issues"),
    col("v.last_issue_id").cast("bigint").alias("last_issue_id"),
    to_timestamp(col("v.date_last_updated")).alias("date_last_updated"),
    to_date(lit(ingestion_date)).alias("ingestion_date"),
    lit(run_id).alias("run_id")
)

volumes_df.createOrReplaceTempView("staging_volumes")

spark.sql(f"""
MERGE INTO glue_catalog.{database}.silver_volumes AS target
USING staging_volumes AS source
ON target.volume_id = source.volume_id
WHEN MATCHED AND source.date_last_updated >= target.date_last_updated THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
""")

spark.sql(f"""
MERGE INTO glue_catalog.{database}.control_volume_state AS target
USING (
    SELECT
        volume_id,
        name,
        date_last_updated,
        count_of_issues,
        last_issue_id,
        current_timestamp() AS last_checked_at,
        run_id
    FROM staging_volumes
) AS source
ON target.volume_id = source.volume_id
WHEN MATCHED AND source.date_last_updated >= target.date_last_updated THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
""")


# -------------------------
# Issues
# -------------------------

raw_issues_df = spark.read.option("multiline", "true").json(issues_path)

issues_df = raw_issues_df.selectExpr("explode(volumes) as volume_entry") \
    .selectExpr(
        "volume_entry.volume_id as parent_volume_id",
        "volume_entry.volume_name as parent_volume_name",
        "explode(volume_entry.issues) as issue"
    ) \
    .select(
        col("issue.id").cast("bigint").alias("issue_id"),
        col("issue.volume.id").cast("bigint").alias("volume_id"),
        col("issue.volume.name").alias("volume_name"),
        col("issue.issue_number").alias("issue_number"),
        col("issue.name").alias("name"),
        to_date(col("issue.cover_date")).alias("cover_date"),
        to_date(col("issue.store_date")).alias("store_date"),
        col("issue.api_detail_url").alias("api_detail_url"),
        col("issue.site_detail_url").alias("site_detail_url"),
        to_timestamp(col("issue.date_added")).alias("date_added"),
        to_timestamp(col("issue.date_last_updated")).alias("date_last_updated"),
        to_date(lit(ingestion_date)).alias("ingestion_date"),
        lit(run_id).alias("run_id")
    )

issues_df.createOrReplaceTempView("staging_issues")

spark.sql(f"""
MERGE INTO glue_catalog.{database}.silver_issues AS target
USING staging_issues AS source
ON target.issue_id = source.issue_id
WHEN MATCHED AND source.date_last_updated >= target.date_last_updated THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
""")


# -------------------------
# Issue details
# -------------------------

# File structure: {"issue_details": [{issue_id, volume_id, fetched_at, raw_detail: {...}}]}
raw_details_df = spark.read.option("multiline", "true").json(issue_details_path)

# Normalise credit arrays: to_json → from_json forces the target schema regardless
# of whether Spark inferred array<struct<...>> or array<string> (all-empty arrays).
details_base_df = raw_details_df.selectExpr("explode(issue_details) as d") \
    .withColumn("char_creds",    from_json(to_json(col("d.raw_detail.character_credits")), _credit_schema)) \
    .withColumn("obj_creds",     from_json(to_json(col("d.raw_detail.object_credits")),   _credit_schema)) \
    .withColumn("person_creds",  from_json(to_json(col("d.raw_detail.person_credits")),   _person_credit_schema)) \
    .withColumn("team_creds",    from_json(to_json(col("d.raw_detail.team_credits")),     _credit_schema)) \
    .withColumn("loc_creds",     from_json(to_json(col("d.raw_detail.location_credits")), _credit_schema)) \
    .withColumn("concept_creds", from_json(to_json(col("d.raw_detail.concept_credits")),  _credit_schema))

details_df = details_base_df.select(
    col("d.raw_detail.id").cast("bigint").alias("issue_id"),
    col("d.raw_detail.volume.id").cast("bigint").alias("volume_id"),
    col("d.raw_detail.volume.name").alias("volume_name"),
    col("d.raw_detail.issue_number").alias("issue_number"),
    col("d.raw_detail.name").alias("name"),
    col("d.raw_detail.description").alias("description"),
    col("d.raw_detail.image.medium_url").alias("image_url"),

    expr("transform(char_creds,    x -> x.name)").alias("characters"),
    expr("transform(obj_creds,     x -> x.name)").alias("objects"),
    expr("transform(filter(person_creds, x -> lower(x.role) like '%writer%'),   x -> x.name)").alias("writers"),
    expr("transform(filter(person_creds, x -> lower(x.role) like '%artist%'),   x -> x.name)").alias("artists"),
    expr("transform(filter(person_creds, x -> lower(x.role) like '%colorist%'), x -> x.name)").alias("colorists"),
    expr("transform(team_creds,    x -> x.name)").alias("teams"),
    expr("transform(loc_creds,     x -> x.name)").alias("locations"),
    expr("transform(concept_creds, x -> x.name)").alias("concepts"),

    col("d.raw_detail.site_detail_url").alias("site_detail_url"),
    col("d.raw_detail.api_detail_url").alias("api_detail_url"),
    to_date(col("d.raw_detail.store_date")).alias("store_date"),
    to_date(col("d.raw_detail.cover_date")).alias("cover_date"),
    to_timestamp(col("d.raw_detail.date_added")).alias("date_added"),
    to_timestamp(col("d.raw_detail.date_last_updated")).alias("date_last_updated"),
    to_timestamp(col("d.fetched_at")).alias("detail_fetched_at"),
    to_date(lit(ingestion_date)).alias("ingestion_date"),
    lit(run_id).alias("run_id")
)

details_df = details_df.withColumn(
    "content_hash",
    sha2(
        concat_ws(
            "||",
            col("issue_id").cast("string"),
            col("volume_id").cast("string"),
            col("name"),
            col("description"),
            col("date_last_updated").cast("string")
        ),
        256
    )
)

details_df.createOrReplaceTempView("staging_issue_details")

spark.sql(f"""
MERGE INTO glue_catalog.{database}.silver_issue_details AS target
USING staging_issue_details AS source
ON target.issue_id = source.issue_id
WHEN MATCHED AND source.date_last_updated >= target.date_last_updated THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
""")


# -------------------------
# Control issue state
# -------------------------

spark.sql(f"""
MERGE INTO glue_catalog.{database}.control_issue_state AS target
USING (
    SELECT
        issue_id,
        volume_id,
        name,
        issue_number,
        date_last_updated,
        detail_fetched_at,
        content_hash,
        run_id
    FROM staging_issue_details
) AS source
ON target.issue_id = source.issue_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
""")

spark.stop()