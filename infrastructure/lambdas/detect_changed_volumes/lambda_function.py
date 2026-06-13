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
CONTROL_VOLUME_TABLE = os.environ["CONTROL_VOLUME_TABLE"]
ATHENA_OUTPUT = os.environ["ATHENA_OUTPUT"]


def write_json_to_s3(bucket, key, body):
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(body, ensure_ascii=False, indent=2),
        ContentType="application/json",
    )


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

    return json.loads(
        response["Body"].read().decode("utf-8")
    )


def run_athena_query(query):
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={
            "Database": ATHENA_DATABASE
        },
        ResultConfiguration={
            "OutputLocation": ATHENA_OUTPUT if ATHENA_OUTPUT.startswith("s3://") else f"s3://{ATHENA_OUTPUT}"
        }
    )

    query_execution_id = response["QueryExecutionId"]

    while True:
        result = athena.get_query_execution(
            QueryExecutionId=query_execution_id
        )

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

    response = s3.get_object(
        Bucket=bucket,
        Key=key
    )

    body = response["Body"].read().decode("utf-8")
    reader = csv.DictReader(StringIO(body))

    return list(reader)


def get_existing_volume_state():
    query = f"""
        SELECT
            volume_id,
            name,
            date_last_updated,
            count_of_issues,
            last_issue_id
        FROM {CONTROL_VOLUME_TABLE}
    """

    query_execution_id = run_athena_query(query)
    rows = read_athena_results(query_execution_id)

    existing_state = {}

    for row in rows:
        volume_id = int(row["volume_id"])

        existing_state[volume_id] = {
            "volume_id": volume_id,
            "name": row.get("name"),
            "date_last_updated": parse_datetime(row.get("date_last_updated")),
            "count_of_issues": int(row["count_of_issues"]) if row.get("count_of_issues") else None,
            "last_issue_id": int(row["last_issue_id"]) if row.get("last_issue_id") else None,
        }

    return existing_state


def get_last_issue_id(volume):
    last_issue = volume.get("last_issue")

    if isinstance(last_issue, dict):
        return last_issue.get("id")

    return volume.get("last_issue_id")


def normalize_volume(volume):
    return {
        "volume_id": int(volume["volume_id"]),
        "name": volume.get("name"),
        "api_detail_url": volume.get("api_detail_url"),
        "site_detail_url": volume.get("site_detail_url"),
        "date_last_updated": volume.get("date_last_updated"),
        "count_of_issues": int(volume["count_of_issues"]) if volume.get("count_of_issues") is not None else None,
        "last_issue_id": int(get_last_issue_id(volume)) if get_last_issue_id(volume) else None,
    }


def detect_change(volume, existing_state):
    volume_id = volume["volume_id"]
    existing = existing_state.get(volume_id)

    if not existing:
        return True, "new_volume"

    api_updated = parse_datetime(volume.get("date_last_updated"))
    stored_updated = existing.get("date_last_updated")

    if api_updated and stored_updated and api_updated > stored_updated:
        return True, "date_last_updated_changed"

    api_count = volume.get("count_of_issues")
    stored_count = existing.get("count_of_issues")

    if api_count is not None and stored_count is not None and api_count > stored_count:
        return True, "issue_count_increased"

    api_last_issue_id = volume.get("last_issue_id")
    stored_last_issue_id = existing.get("last_issue_id")

    if api_last_issue_id and stored_last_issue_id and api_last_issue_id != stored_last_issue_id:
        return True, "last_issue_changed"

    return False, "unchanged"


def lambda_handler(event, context):
    run_id = event["run_id"]
    volumes_key = event["volumes_key"]

    raw_volumes = read_json_from_s3(volumes_key)["volumes"]
    existing_state = get_existing_volume_state()

    changed_volumes = []
    unchanged_volumes = []

    for raw_volume in raw_volumes:
        volume = normalize_volume(raw_volume)
        changed, reason = detect_change(volume, existing_state)

        volume["change_reason"] = reason

        if changed:
            changed_volumes.append(volume)
        else:
            unchanged_volumes.append(volume)

    bronze_prefix = event["bronze_prefix"]

    changed_key = f"{bronze_prefix}changed_volumes.json"
    unchanged_key = f"{bronze_prefix}unchanged_volumes.json"

    write_json_to_s3(BRONZE_BUCKET, changed_key, {"volumes": changed_volumes})
    write_json_to_s3(BRONZE_BUCKET, unchanged_key, {"volumes": unchanged_volumes})

    return {
        **event,
        "input_volume_count": len(raw_volumes),
        "existing_volume_count": len(existing_state),
        "changed_volume_count": len(changed_volumes),
        "unchanged_volume_count": len(unchanged_volumes),
        "changed_volumes_key": changed_key,
        "unchanged_volumes_key": unchanged_key,
    }