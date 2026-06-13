"""
Lambda: fetch_changed_issue_details

For each issue in the changed-issues list, fetches the full detail record
from the ComicVine API, writes all results to a single JSON file in Bronze
S3, and writes a run manifest.

Environment variables:
    API_KEY       - ComicVine API key
    BUCKET_BRONZE - S3 bucket name for the bronze layer

Step Functions input:
    {
        "run_id": str,
        "ingestion_date": str,       # YYYY-MM-DD
        "changed_issues_key": str    # S3 key of the changed-issues file
    }

Step Functions output (input forwarded plus):
    {
        "issue_details_prefix": str,
        "issue_details_manifest_key": str,
        "issue_details_key": str,
        "failed_issues_key": str,
        "successful_detail_count": int,
        "failed_detail_count": int
    }
"""

import os
import json
import random
import boto3
import requests
from datetime import datetime, timezone
from time import sleep


BASE_URL = "https://comicvine.gamespot.com/api"
HEADERS  = {"User-Agent": "absolutePipeline"}

s3_client = boto3.client("s3")


def read_json_from_s3(bucket, key):
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return json.loads(response["Body"].read().decode("utf-8"))


def write_json_to_s3(bucket, key, body) -> None:
    """Serializes body as JSON and writes it to s3://bucket/key."""
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(body, ensure_ascii=False, indent=2),
        ContentType="application/json",
    )


def call_comicvine_url(url, params):
    """GETs a full ComicVine URL and returns the parsed JSON response."""
    response = requests.get(url=url, params=params, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def fetch_issue_detail(issue, api_key):
    response_json = call_comicvine_url(
        url=issue["api_detail_url"],
        params={
            "api_key": api_key,
            "format": "json",
            "field_list": (
                "id,name,issue_number,date_added,date_last_updated,"
                "store_date,cover_date,site_detail_url,api_detail_url,"
                "description,image,volume,character_credits,"
                "object_credits,person_credits,team_credits,"
                "location_credits,concept_credits"
            ),
        },
    )

    return {
        "issue_id":            issue["issue_id"],
        "volume_id":           issue["volume_id"],
        "volume_name":         issue.get("volume_name"),
        "change_reason":       issue.get("change_reason"),
        "fetched_at":          datetime.now(timezone.utc).isoformat(),
        "source_issue_summary": issue,
        "raw_detail":          response_json["results"],
    }


def lambda_handler(event, context):
    # Read config from environment
    API_KEY = os.environ["API_KEY"]
    BUCKET  = os.environ["BUCKET_BRONZE"]

    run_id              = event["run_id"]
    ingestion_date      = event["ingestion_date"]
    changed_issues_key  = event["changed_issues_key"]

    changed_issues = read_json_from_s3(BUCKET, changed_issues_key)

    output_prefix = (
        f"issue_details/"
        f"ingestion_date={ingestion_date}/"
        f"run_id={run_id}/"
    )

    issue_details  = []
    failed_issues  = []
    total_api_calls = 0

    for issue in changed_issues:
        try:
            print(f"Fetching issue detail {issue['issue_id']} - {issue.get('name')}")

            detail = fetch_issue_detail(issue, API_KEY)
            issue_details.append(detail)
            total_api_calls += 1

        except Exception as exc:
            print(f"Failed issue {issue.get('issue_id')}: {exc}")

            failed_issues.append({
                "issue_id":       issue.get("issue_id"),
                "volume_id":      issue.get("volume_id"),
                "name":           issue.get("name"),
                "api_detail_url": issue.get("api_detail_url"),
                "error":          str(exc),
            })

        sleep(random.randint(2, 5))

    # Write all fetched details into a single file
    issue_details_key = f"{output_prefix}issue_details.json"
    write_json_to_s3(BUCKET, issue_details_key, {
        "run_id":          run_id,
        "ingestion_date":  ingestion_date,
        "detail_count":    len(issue_details),
        "issue_details":   issue_details,
    })

    # Write failures so they can be retried or investigated
    failed_issues_key = f"{output_prefix}failed_issues.json"
    write_json_to_s3(BUCKET, failed_issues_key, {
        "run_id":        run_id,
        "ingestion_date": ingestion_date,
        "failed_count":  len(failed_issues),
        "failed_issues": failed_issues,
    })

    # Write run manifest to Bronze for auditing and reprocessing
    manifest = {
        "run_id":                   run_id,
        "entity":                   "issue_details",
        "source":                   "comicvine",
        "ingestion_date":           ingestion_date,
        "created_at":               datetime.now(timezone.utc).isoformat(),
        "api_calls":                total_api_calls,
        "input_changed_issue_count": len(changed_issues),
        "successful_detail_count":  len(issue_details),
        "failed_detail_count":      len(failed_issues),
        "issue_details_key":        issue_details_key,
        "failed_issues_key":        failed_issues_key,
    }

    manifest_key = f"{output_prefix}manifest.json"
    write_json_to_s3(BUCKET, manifest_key, manifest)

    return {
        **event,
        "issue_details_prefix":       output_prefix,
        "issue_details_manifest_key": manifest_key,
        "issue_details_key":          issue_details_key,
        "failed_issues_key":          failed_issues_key,
        "successful_detail_count":    len(issue_details),
        "failed_detail_count":        len(failed_issues),
    }
