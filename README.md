# DC Absolute Data Pipeline

![Absolute Batman](img/banner2.png)

An automated ingestion and transformation pipeline for DC Comics' Absolute Universe titles. It fetches volume and issue data from the [ComicVine API](https://comicvine.gamespot.com/api/), detects what has changed since the last run, upserts the results into Iceberg tables on AWS, and sends an email digest via SES.

## Architecture

```
ComicVine API
     │
     ▼
┌─────────────────────┐
│  Step Functions     │  Orchestrates the full pipeline run
│  State Machine      │
└─────────────────────┘
     │
     ├─► Fetch Volumes          Lambda — fetches all Absolute Universe volumes
     │
     ├─► Check Changed Volumes  Lambda — diffs against control table via Athena
     │                          (exits early if nothing changed)
     ├─► Fetch Issues           Lambda — fetches all issues for changed volumes
     │
     ├─► Check Changed Issues   Lambda — diffs against control table via Athena
     │                          (exits early if nothing changed)
     ├─► Fetch Issues Details   Lambda — fetches full detail record per changed issue
     │
     ├─► Bronze to Silver       Glue job — transforms raw JSON into Iceberg tables
     │
     └─► Send Notification      Lambda — sends an SES email digest on every run;
                                content adapts to what changed (or "no changes")
```

### S3 layers

| Bucket           | Purpose                                                                            |
| ---------------- | ---------------------------------------------------------------------------------- |
| `bronze`         | Raw JSON responses from ComicVine, keyed by `ingestion_date` and `run_id`          |
| `silver`         | Cleaned Iceberg tables (`silver_volumes`, `silver_issues`, `silver_issue_details`) |
| `control`        | Iceberg control tables that track the last-known state of each volume and issue    |
| `glue-scripts`   | Uploaded Glue job script                                                           |
| `athena-results` | Athena query result output                                                         |

### Lambda functions

| Function                           | Description                                                                                                                  |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `fetch_volumes`                    | Pages through the ComicVine API filtering for DC Absolute Universe volumes (2024+), writes `filtered_volumes.json` to bronze |
| `detect_changed_volumes`           | Queries the `control_volume_state` Iceberg table via Athena and splits volumes into `changed` / `unchanged`                  |
| `fetch_issues_for_changed_volumes` | Fetches all issues for each changed volume (paginated), writes a single `issues.json` grouped by volume                      |
| `detect_changed_issues`            | Queries the `control_issue_state` Iceberg table via Athena and splits issues into `changed` / `unchanged`                    |
| `fetch_changed_issue_details`      | Fetches the full detail record for each changed issue via its `api_detail_url`                                               |
| `send_pipeline_notification`       | Reads the current run's bronze files and sends an HTML email via SES with updated volumes and new issues                     |

### Glue job — `bronze_to_silver`

Reads the three bronze files written by the current run and upserts into Iceberg tables using `MERGE INTO`:

- `silver_volumes` — volume metadata
- `silver_issues` — issue summaries
- `silver_issue_details` — full issue details including credits (characters, writers, artists, etc.)
- `control_volume_state` — updated last-seen state for each volume
- `control_issue_state` — updated last-seen state + content hash for each issue

### SES notification

The `send_pipeline_notification` Lambda runs at the end of every execution — including early exits — and sends an HTML email with a random banner from the assets bucket. The content adapts to what actually happened:

| Scenario | Email content |
| -------- | ------------- |
| No changed volumes | "No changes detected this run." |
| Changed volumes, no new issues | Updated Volumes table |
| Changed volumes + new issues | Updated Volumes table + New Issues card grid (cover image, volume name, issue number, title, store date) |

Both the sender and recipient addresses must be verified in SES (or the account must be out of sandbox mode for the recipient).

## Prerequisites

- AWS account with permissions to create Lambda, Glue, Step Functions, S3, IAM, Glue Catalog, and SES resources
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.3.0
- A [ComicVine API key](https://comicvine.gamespot.com/api/)
- A verified SES sender email address

## Deploy

**1. Copy and fill in the variables file**

```bash
cp infrastructure/terraform.tfvars.example infrastructure/terraform.tfvars
```

Edit `terraform.tfvars` — the required values are:

| Variable                                          | Description                                                                                                               |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `api_key`                                         | ComicVine API key                                                                                                         |
| `s3_bronze_bucket`                                | Globally unique S3 bucket name for bronze layer                                                                           |
| `s3_silver_bucket`                                | Globally unique S3 bucket name for silver layer                                                                           |
| `s3_gold_bucket`                                  | Globally unique S3 bucket name for gold layer                                                                             |
| `s3_control_bucket`                               | Globally unique S3 bucket name for control tables                                                                         |
| `glue_scripts_bucket`                             | Globally unique S3 bucket name for Glue scripts                                                                           |
| `athena_query_results_bucket`                     | Globally unique S3 bucket name for Athena results                                                                         |
| `glue_warehouse_path`                             | S3 path for the Iceberg warehouse root (e.g. `s3://your-silver-bucket/warehouse/`)                                        |
| `aws_wrangler_layer_arn`                          | ARN of the [AWS SDK for pandas Lambda layer](https://aws-sdk-pandas.readthedocs.io/en/stable/layers.html) for your region |
| `s3_assets_bucket`                                | Globally unique S3 bucket name for public static assets (banner images)                                                   |
| `ses_sender_email`                                | Verified SES email address used as the notification sender                                                                |
| `ses_recipient_email`                             | Email address that receives the pipeline run notification                                                                 |
| `lambda_function_name_send_pipeline_notification` | Name for the notification Lambda function                                                                                 |

**2. Apply**

```bash
cd infrastructure
terraform init
terraform apply
```

## Running the pipeline

Trigger a run from the AWS console or CLI:

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:<account-id>:stateMachine:dc-absolute-pipeline \
  --input '{}'
```

Each execution:

1. Generates a unique `run_id` (timestamp + UUID) and `ingestion_date`
2. Skips all downstream steps automatically if no volumes or issues have changed
3. Writes all bronze files under `<entity>/ingestion_date=YYYY-MM-DD/run_id=.../`
4. Sends an email notification after a successful Glue run

To re-send the notification for a previous run without re-fetching data, invoke the Lambda directly with the bronze keys from that run:

```bash
aws lambda invoke \
  --region us-east-1 \
  --function-name dc-absolute-send-pipeline-notification \
  --payload '{
    "run_id": "<run_id>",
    "ingestion_date": "<YYYY-MM-DD>",
    "volumes_key": "volumes/ingestion_date=<date>/run_id=<run_id>/changed_volumes.json",
    "issue_details_key": "issue_details/ingestion_date=<date>/run_id=<run_id>/issue_details.json"
  }' \
  --cli-binary-format raw-in-base64-out \
  /tmp/response.json
```

## Project structure

```
infrastructure/
  lambdas/
    fetch_volumes/
    detect_changed_volumes/
    fetch_issues_for_changed_volumes/
    detect_changed_issues/
    fetch_changed_issue_details/
    send_pipeline_notification/
  glue_jobs/
    bronze_to_silver.py
  state_machines/
    ingestion.json          # Step Functions definition (templatefile)
  main.tf
  lambda.tf
  glue.tf
  stepfunctions.tf
  iam.tf
  s3.tf
  variables.tf
  terraform.tfvars.example
samples/                    # Example bronze JSON files for local development
```
