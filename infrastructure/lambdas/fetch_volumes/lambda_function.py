"""
Lambda: fetch_volumes

Fetches all DC Absolute Universe volumes from the ComicVine API,
writes each raw page response to Bronze S3, and returns a filtered
list of volumes to the Step Functions state machine.

Environment variables:
    API_KEY       - ComicVine API key (from Secrets Manager)
    BUCKET_BRONZE - S3 bucket name for the bronze layer

Step Functions output:
    {
        "run_id": str,
        "ingestion_date": str,          # YYYY-MM-DD
        "bronze_prefix": str,           # S3 prefix for this run's raw pages
        "manifest_key": str,            # S3 key of the run manifest
        "volume_count": int,
        "volumes": [
            {
                "volume_id": int,
                "name": str,
                "api_detail_url": str,
                "date_last_updated": str,
                "count_of_issues": int,
                "last_issue_id": int | None
            }
        ]
    }
"""

import os
import json
import uuid
import boto3
from datetime import datetime, timezone
from time import sleep
import random
import requests

BASE_URL = "https://comicvine.gamespot.com/api"
HEADERS = {"User-Agent": "absolutePipeline"}

s3_client = boto3.client("s3")


def current_utc_datetime() -> datetime:
    return datetime.now(timezone.utc)


def utc_timestamp_plus_uuid() -> str:
    """Returns a sortable unique ID: <YYYYMMDDTHHmmss>-<8-char hex>."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


def call_comicvine_api(endpoint: str, params: dict) -> dict:
    """GETs a ComicVine endpoint and returns the parsed JSON response."""
    url = BASE_URL + endpoint
    response = requests.get(url=url, params=params, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def write_json_to_s3(bucket: str, key: str, body: dict) -> None:
    """Serializes body as JSON and writes it to s3://bucket/key."""
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(body, ensure_ascii=False, indent=2),
        ContentType="application/json",
    )


def lambda_handler(event, context):
    # Read config from environment
    API_KEY = os.environ["API_KEY"]
    BUCKET  = os.environ["BUCKET_BRONZE"]

    # Create a unique run ID and capture ingestion timestamp
    now = current_utc_datetime()
    ingestion_date = now.date()
    run_id = utc_timestamp_plus_uuid()

    offset = 0
    limit = 100
    all_filtered_volumes = []
    s3_objects = []
    api_calls = 0

    # Paginate through all ComicVine volume results
    while True:
        response_json = call_comicvine_api(
            endpoint="/volumes",
            params={
                "api_key": API_KEY,
                "format": "json",
                "filter": "name:Absolute",
                "limit": limit,
                "offset": offset
            },
        )
        api_calls += 1

        # Keep only DC Comics Absolute Universe titles from 2024 onwards

        # Write raw page to Bronze before any filtering -- NOISY 
        # s3_key = (
        #     f"bronze/comicvine/volumes/"
        #     f"ingestion_date={ingestion_date}/"
        #     f"run_id={run_id}/"
        #     f"page_offset={offset}.json"
        # )
        # write_json_to_s3(bucket=BUCKET, key=s3_key, body=response_json)
        # s3_objects.append(s3_key)

        for volume in response_json["results"]:
            publisher_name = volume["publisher"]["name"]
            start_year = int(volume["start_year"])
            volume_name = volume["name"]

            if publisher_name != "DC Comics":
                continue
            if start_year < 2024:
                continue
            if "Absolute Power" in volume_name:
                continue

            all_filtered_volumes.append(volume)

        # Stop paginating when all results have been fetched
        total_results = response_json["number_of_total_results"]
        if offset + limit >= total_results:
            break

        offset += limit
        sleep(random.randint(2, 5))

    # Write run manifest to Bronze for auditing and reprocessing
    manifest = {
        "run_id": run_id,
        "entity": "volumes",
        "source": "comicvine",
        "ingestion_date": str(ingestion_date),
        "created_at": now.isoformat(),
        "filter": {
            "name": "Absolute",
            "publisher": "DC Comics",
            "min_start_year": 2024,
            "excluded_names": ["Absolute Power"]
        },
        #"raw_objects": s3_objects,
        "api_calls": api_calls,
        "total_results": total_results,
        "volume_count": len(all_filtered_volumes),
        "volume_ids": [v["id"] for v in all_filtered_volumes]
    }

    manifest_key = (
        f"bronze/comicvine/volumes/"
        f"ingestion_date={ingestion_date}/"
        f"run_id={run_id}/"
        f"manifest.json"
    )
    write_json_to_s3(BUCKET, manifest_key, manifest)

    # Write filtered volumes to S3 — Step Functions has a 256 KB payload limit
    # so the next Lambda reads from this key instead of the state input
    volumes_key = (
        f"bronze/comicvine/volumes/"
        f"ingestion_date={ingestion_date}/"
        f"run_id={run_id}/"
        f"filtered_volumes.json"
    )
    write_json_to_s3(BUCKET, volumes_key, {
        "volumes": [
            {
                "volume_id": v["id"],
                "name": v["name"],
                "api_detail_url": v["api_detail_url"],
                "date_last_updated": v["date_last_updated"],
                "count_of_issues": v["count_of_issues"],
                "last_issue_id": v.get("last_issue", {}).get("id")
            }
            for v in all_filtered_volumes
        ]
    })

    return {
        "run_id": run_id,
        "ingestion_date": str(ingestion_date),
        "bronze_prefix": (
            f"bronze/comicvine/volumes/"
            f"ingestion_date={ingestion_date}/"
            f"run_id={run_id}/"
        ),
        "manifest_key": manifest_key,
        "volumes_key": volumes_key,
        "volume_count": len(all_filtered_volumes),
    }
