"""
Lambda: fetch_issues_for_changed_volumes

For each volume in the changed-volumes list, fetches all issues from the
ComicVine API (paginated), writes a per-volume JSON file to Bronze S3, and
writes a run manifest.

Environment variables:
    API_KEY       - ComicVine API key
    BUCKET_BRONZE - S3 bucket name for the bronze layer

Step Functions input:
    {
        "run_id": str,
        "ingestion_date": str,        # YYYY-MM-DD
        "changed_volumes_key": str    # S3 key of the changed-volumes file
    }

Step Functions output (input forwarded plus):
    {
        "issues_prefix": str,
        "issues_manifest_key": str,
        "changed_volume_count": int,
        "total_issue_count": int,
        "issue_files": [
            {
                "volume_id": int,
                "volume_name": str,
                "issue_count": int,
                "issues_key": str
            }
        ]
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
HEADERS = {"User-Agent": "absolutePipeline"}
LIMIT = 100

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


def call_comicvine_api(endpoint, params):
    """GETs a ComicVine endpoint and returns the parsed JSON response."""
    url = BASE_URL + endpoint
    response = requests.get(url=url, params=params, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def fetch_issues_for_volume(volume_id, api_key):
    all_issues = []
    offset = 0
    api_calls = 0

    while True:
        response_json = call_comicvine_api(
            endpoint="/issues/",
            params={
                "api_key": api_key,
                "format": "json",
                "filter": f"volume:{volume_id}",
                "field_list": (
                    "api_detail_url,id,name,site_detail_url,issue_number,"
                    "date_added,date_last_updated,store_date,cover_date,volume"
                ),
                "limit": LIMIT,
                "offset": offset,
            },
        )
        api_calls += 1

        results = response_json.get("results", [])
        all_issues.extend(results)

        total_results = response_json.get("number_of_total_results", 0)
        if len(all_issues) >= total_results:
            break

        offset += LIMIT
        sleep(random.randint(2, 5))

    return all_issues, api_calls


def lambda_handler(event, context):
    # Read config from environment
    API_KEY = os.environ["API_KEY"]
    BUCKET  = os.environ["BUCKET_BRONZE"]

    run_id               = event["run_id"]
    ingestion_date       = event["ingestion_date"]
    changed_volumes_key  = event["changed_volumes_key"]

    changed_volumes = read_json_from_s3(BUCKET, changed_volumes_key)["volumes"]

    issues_prefix = (
        f"issues/"
        f"ingestion_date={ingestion_date}/"
        f"run_id={run_id}/"
    )

    all_volume_issues = []
    total_issue_count = 0
    total_api_calls   = 0

    for volume in changed_volumes:
        volume_id   = volume["volume_id"]
        volume_name = volume.get("name")

        print(f"Fetching issues for volume {volume_id} - {volume_name}")

        issues, api_calls = fetch_issues_for_volume(volume_id=volume_id, api_key=API_KEY)
        total_api_calls   += api_calls
        total_issue_count += len(issues)

        all_volume_issues.append({
            "volume_id":   volume_id,
            "volume_name": volume_name,
            "issue_count": len(issues),
            "issues":      issues,
        })

        sleep(random.randint(2, 5))

    # Write all issues for this run into a single file
    issues_key = f"{issues_prefix}issues.json"
    write_json_to_s3(BUCKET, issues_key, {
        "run_id":          run_id,
        "ingestion_date":  ingestion_date,
        "total_issue_count": total_issue_count,
        "volumes":         all_volume_issues,
    })

    # Write run manifest to Bronze for auditing and reprocessing
    manifest = {
        "run_id":               run_id,
        "entity":               "issues",
        "source":               "comicvine",
        "ingestion_date":       ingestion_date,
        "created_at":           datetime.now(timezone.utc).isoformat(),
        "api_calls":            total_api_calls,
        "changed_volume_count": len(changed_volumes),
        "total_issue_count":    total_issue_count,
        "issues_key":           issues_key,
    }

    manifest_key = f"{issues_prefix}manifest.json"
    write_json_to_s3(BUCKET, manifest_key, manifest)

    return {
        **event,
        "issues_prefix":        issues_prefix,
        "issues_manifest_key":  manifest_key,
        "issues_key":           issues_key,
        "changed_volume_count": len(changed_volumes),
        "total_issue_count":    total_issue_count,
    }
