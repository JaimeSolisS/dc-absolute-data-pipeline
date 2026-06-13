import os
import json
import csv
import time
from io import StringIO
from datetime import datetime

import boto3


s3 = boto3.client("s3")
athena = boto3.client("athena")


BRONZE_BUCKET = os.environ["BRONZE_BUCKET"]
ATHENA_DATABASE = os.environ["ATHENA_DATABASE"]
CONTROL_ISSUE_TABLE = os.environ["CONTROL_ISSUE_TABLE"]
ATHENA_OUTPUT = os.environ["ATHENA_OUTPUT"]


def parse_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    value = str(value).replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def read_json_from_s3(key):
    response = s3.get_object(
        Bucket=BRONZE_BUCKET,
        Key=key
    )
    return json.loads(response["Body"].read().decode("utf-8"))


def write_json_to_s3(bucket, key, body):
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json"
    )


def run_athena_query(query):
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": ATHENA_DATABASE},
        ResultConfiguration={
            "OutputLocation": ATHENA_OUTPUT if ATHENA_OUTPUT.startswith("s3://") else f"s3://{ATHENA_OUTPUT}"
        }
    )

    query_execution_id = response["QueryExecutionId"]

    while True:
        result = athena.get_query_execution(QueryExecutionId=query_execution_id)
        state = result["QueryExecution"]["Status"]["State"]

        if state == "SUCCEEDED":
            return query_execution_id

        if state in ["FAILED", "CANCELLED"]:
            reason = result["QueryExecution"]["Status"].get("StateChangeReason")
            raise RuntimeError(f"Athena query {state}: {reason}")

        time.sleep(1)


def read_athena_results(query_execution_id):
    output_location = ATHENA_OUTPUT.rstrip("/")
    result_s3_path = f"{output_location}/{query_execution_id}.csv"

    bucket_key = result_s3_path.replace("s3://", "")
    bucket, key = bucket_key.split("/", 1)

    response = s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read().decode("utf-8")

    return list(csv.DictReader(StringIO(body)))


def get_existing_issue_state():
    query = f"""
        SELECT
            issue_id,
            volume_id,
            date_last_updated,
            detail_fetched_at
        FROM {CONTROL_ISSUE_TABLE}
    """

    query_execution_id = run_athena_query(query)
    rows = read_athena_results(query_execution_id)

    existing_state = {}

    for row in rows:
        issue_id = int(row["issue_id"])

        existing_state[issue_id] = {
            "issue_id": issue_id,
            "volume_id": int(row["volume_id"]) if row.get("volume_id") else None,
            "date_last_updated": parse_datetime(row.get("date_last_updated")),
            "detail_fetched_at": parse_datetime(row.get("detail_fetched_at")),
        }

    return existing_state


def flatten_issues(issues_payload):
    flattened = []

    for volume_entry in issues_payload.get("volumes", []):
        volume_id = volume_entry.get("volume_id")
        volume_name = volume_entry.get("volume_name")

        for issue in volume_entry.get("issues", []):
            issue_volume = issue.get("volume") or {}

            flattened.append({
                "issue_id": int(issue["id"]),
                "volume_id": int(issue_volume.get("id") or volume_id),
                "volume_name": issue_volume.get("name") or volume_name,
                "name": issue.get("name"),
                "issue_number": issue.get("issue_number"),
                "api_detail_url": issue.get("api_detail_url"),
                "site_detail_url": issue.get("site_detail_url"),
                "date_added": issue.get("date_added"),
                "date_last_updated": issue.get("date_last_updated"),
                "store_date": issue.get("store_date"),
                "cover_date": issue.get("cover_date"),
            })

    return flattened


def detect_change(issue, existing_state):
    issue_id = issue["issue_id"]
    existing = existing_state.get(issue_id)

    if not existing:
        return True, "new_issue"

    api_updated = parse_datetime(issue.get("date_last_updated"))
    stored_updated = existing.get("date_last_updated")

    if api_updated and stored_updated and api_updated > stored_updated:
        return True, "date_last_updated_changed"

    if existing.get("detail_fetched_at") is None:
        return True, "missing_detail_fetch"

    return False, "unchanged"


def lambda_handler(event, context):
    run_id = event["run_id"]
    ingestion_date = event["ingestion_date"]
    issues_key = event["issues_key"]

    issues_payload = read_json_from_s3(issues_key)
    issues = flatten_issues(issues_payload)

    existing_state = get_existing_issue_state()

    changed_issues = []
    unchanged_issues = []

    for issue in issues:
        changed, reason = detect_change(issue, existing_state)
        issue["change_reason"] = reason

        if changed:
            changed_issues.append(issue)
        else:
            unchanged_issues.append(issue)

    output_prefix = f"issues/ingestion_date={ingestion_date}/run_id={run_id}/"

    changed_issues_key = f"{output_prefix}changed_issues.json"
    unchanged_issues_key = f"{output_prefix}unchanged_issues.json"

    write_json_to_s3(BRONZE_BUCKET, changed_issues_key, changed_issues)
    write_json_to_s3(BRONZE_BUCKET, unchanged_issues_key, unchanged_issues)

    return {
        **event,
        "input_issue_count": len(issues),
        "existing_issue_count": len(existing_state),
        "changed_issue_count": len(changed_issues),
        "unchanged_issue_count": len(unchanged_issues),
        "changed_issues_key": changed_issues_key,
        "unchanged_issues_key": unchanged_issues_key
    }