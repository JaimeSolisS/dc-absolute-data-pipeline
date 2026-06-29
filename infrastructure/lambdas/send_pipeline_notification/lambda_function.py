"""
Lambda: send_pipeline_notification

Reads the bronze volumes and issue_details files written during the current run,
then sends an HTML digest email via SES summarising:
  - Updated volumes (name + issue count)
  - New issues (cover image, volume name, issue number, issue name)

Environment variables:
    BUCKET_BRONZE  - S3 bucket name for the bronze layer
    SES_SENDER     - Verified SES sender email address
    SES_RECIPIENT  - Recipient email address

Step Functions input (full pipeline state, forwarded from Bronze to Silver):
    {
        "run_id": str,
        "ingestion_date": str,
        "volumes_key": str,
        "issue_details_key": str,
        ...
    }
"""

import os
import json
import random
import boto3

s3_client = boto3.client("s3")
ses_client = boto3.client("ses")

BUCKET = os.environ["BUCKET_BRONZE"]
SES_SENDER = os.environ["SES_SENDER"]
SES_RECIPIENT = os.environ["SES_RECIPIENT"]
ASSETS_BUCKET = os.environ["ASSETS_BUCKET"]

BANNER_KEYS = [
    "banners/banner.png", "banners/banner2.png", "banners/banner3.png",
    "banners/banner4.png", "banners/banner5.png", "banners/banner6.png",
]


def random_banner_url():
    key = random.choice(BANNER_KEYS)
    return f"https://{ASSETS_BUCKET}.s3.amazonaws.com/{key}"


def read_json_from_s3(key):
    response = s3_client.get_object(Bucket=BUCKET, Key=key)
    return json.loads(response["Body"].read().decode("utf-8"))


def build_html(run_id, ingestion_date, volumes, new_issues, banner_url):
    volume_rows = "".join(
        f"<tr><td style='padding:6px 12px;border-bottom:1px solid #eee'>{v['name']}</td>"
        f"<td style='padding:6px 12px;border-bottom:1px solid #eee;text-align:center'>{v['count_of_issues']}</td></tr>"
        for v in volumes
    )

    issue_cards = ""
    for issue in new_issues:
        raw = issue.get("raw_detail", {})
        name = raw.get("name") or "Untitled"
        number = raw.get("issue_number", "")
        volume_name = (raw.get("volume") or {}).get("name", issue.get("volume_name", ""))
        image_url = (raw.get("image") or {}).get("medium_url", "")
        store_date = raw.get("store_date") or ""
        img_tag = (
            f"<img src='{image_url}' alt='cover' width='120' "
            f"style='display:block;border-radius:4px;margin-bottom:8px'>"
            if image_url else ""
        )
        issue_cards += f"""
        <div style='display:inline-block;vertical-align:top;width:140px;margin:8px;
                    text-align:center;font-size:13px;color:#333'>
            {img_tag}
            <strong>{volume_name}</strong><br>
            #{number} — {name}<br>
            <span style='color:#777;font-size:11px'>{store_date}</span>
        </div>"""

    if volumes:
        issues_html = issue_cards if new_issues else "<p style='color:#777'>No new issues this run.</p>"
        body_html = f"""
  <h3 style='border-bottom:2px solid #1a1a2e;padding-bottom:4px'>
    Updated Volumes ({len(volumes)})
  </h3>
  <table style='border-collapse:collapse;width:100%'>
    <thead>
      <tr style='background:#1a1a2e;color:#fff'>
        <th style='padding:8px 12px;text-align:left'>Volume</th>
        <th style='padding:8px 12px'>Issue Count</th>
      </tr>
    </thead>
    <tbody>{volume_rows}</tbody>
  </table>
  <h3 style='border-bottom:2px solid #1a1a2e;padding-bottom:4px;margin-top:32px'>
    New Issues ({len(new_issues)})
  </h3>
  <div>{issues_html}</div>"""
    else:
        body_html = "<p style='color:#777;font-size:16px'>No changes detected on this run.</p>"

    return f"""<!DOCTYPE html>
<html>
<body style='font-family:Arial,sans-serif;color:#222;max-width:800px;margin:auto;padding:20px'>
  <h2 style='color:#1a1a2e'>DC Absolute Pipeline — Run Complete</h2>
  <p style='color:#555'>Run ID: <code>{run_id}</code> &nbsp;|&nbsp; Date: {ingestion_date}</p>
  <div style='text-align:center;margin-bottom:16px'>
    <img src='{banner_url}' alt='DC Absolute' style='max-width:100%;border-radius:6px'>
  </div>
  {body_html}
</body>
</html>"""


def lambda_handler(event, context):
    run_id = event["run_id"]
    ingestion_date = event["ingestion_date"]

    volumes_key = event.get("volumes_key")
    issue_details_key = event.get("issue_details_key")
    has_changes = event.get("changed_volume_count", 0) > 0

    volumes = []
    if has_changes and volumes_key:
        volumes = read_json_from_s3(volumes_key).get("volumes", [])

    new_issues = []
    if has_changes and issue_details_key:
        all_details = read_json_from_s3(issue_details_key).get("issue_details", [])
        new_issues = [d for d in all_details if d.get("change_reason") == "new_issue"]

    html_body = build_html(run_id, ingestion_date, volumes, new_issues, random_banner_url())
    text_body = (
        f"DC Absolute Pipeline complete.\n"
        f"Run: {run_id} | Date: {ingestion_date}\n"
        + (f"Updated volumes: {len(volumes)}\nNew issues: {len(new_issues)}" if has_changes else "No changes detected.")
    )

    ses_client.send_email(
        Source=SES_SENDER,
        Destination={"ToAddresses": [SES_RECIPIENT]},
        Message={
            "Subject": {
                "Data": (
                    f"[DC Absolute] Pipeline complete — {ingestion_date} ({len(new_issues)} new issues)"
                    if has_changes else
                    f"[DC Absolute] No changes detected — {ingestion_date}"
                ),
                "Charset": "UTF-8",
            },
            "Body": {
                "Text": {"Data": text_body, "Charset": "UTF-8"},
                "Html": {"Data": html_body, "Charset": "UTF-8"},
            },
        },
    )

    print(f"Notification sent: {len(volumes)} volumes, {len(new_issues)} new issues")
    return {**event, "notification_sent": True}
