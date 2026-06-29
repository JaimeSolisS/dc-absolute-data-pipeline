import requests
from dotenv import load_dotenv
import os
import json
import pandas as pd
import time

load_dotenv()

API_KEY = os.getenv("API_KEY")
BASE_URL = "https://comicvine.gamespot.com/api/"
HEADERS = {"User-Agent": "absolutePipeline"}
SLEEP = 1


def fetch_volumes(api_key):
    url = BASE_URL + "volumes/"
    all_results = []
    offset = 0
    limit = 100
    api_calls = 0

    while True:
        params = {
            "api_key": api_key,
            "format": "json",
            "filter": "name:Absolute",
            "limit": limit,
            "offset": offset,
        }
        response = requests.get(url=url, params=params, headers=HEADERS)
        data = response.json()
        api_calls += 1
        print(f"api calls: {api_calls}")

        results = data["results"]
        all_results.extend(results)
        print(f"Fetched {len(results)} records. Total: {len(all_results)}")

        if len(all_results) >= data["number_of_total_results"]:
            break

        offset += limit

    print(f"Final count: {len(all_results)}")
    return all_results


def filter_volumes(raw: list[dict]) -> pd.DataFrame:
    df = pd.json_normalize(raw, sep="_")
    df["start_year"] = df["start_year"].astype(int)
    df = df[df["start_year"] >= 2024]
    df = df[df["publisher_name"] == "DC Comics"]
    df = df[~df["name"].str.contains("Absolute Power", na=False)]
    return df[[
        "api_detail_url", "count_of_issues", "date_added", "date_last_updated",
        "description", "id", "name", "site_detail_url", "start_year",
        "first_issue_api_detail_url", "first_issue_id", "first_issue_name",
        "first_issue_issue_number", "image_medium_url", "last_issue_api_detail_url",
        "last_issue_id", "last_issue_name", "last_issue_issue_number",
        "publisher_api_detail_url", "publisher_id", "publisher_name",
    ]]


def fetch_issues_for_volumes(volumes_df: pd.DataFrame, api_key: str) -> pd.DataFrame:
    params = {"api_key": api_key, "format": "json", "field_list": "issues"}
    all_issues = pd.DataFrame(columns=["api_detail_url", "id", "name", "site_detail_url", "issue_number"])

    for row in volumes_df.itertuples():
        print(f"{row.Index} getting issues of {row.name} at {row.api_detail_url}...")
        response = requests.get(url=row.api_detail_url, params=params, headers=HEADERS)
        data = response.json()
        issues_df = pd.DataFrame(data["results"]["issues"])
        all_issues = pd.concat([all_issues, issues_df], ignore_index=True)
        time.sleep(SLEEP)

    return all_issues


def fetch_issue_details(issues_df: pd.DataFrame, api_key: str) -> pd.DataFrame:
    params = {
        "api_key": api_key,
        "format": "json",
        "field_list": "date_last_updated,character_credits,description,id,image,object_credits,person_credits,store_date,volume",
    }

    for col in ["characters", "objects", "colorists", "artists", "writers"]:
        issues_df[col] = None

    for row in issues_df.itertuples():
        print(f"{row.Index} getting data of issue {row.name} at {row.api_detail_url}...")
        response = requests.get(url=issues_df["api_detail_url"][row.Index], params=params, headers=HEADERS)
        data = response.json()["results"]

        persons = data["person_credits"]
        issues_df.at[row.Index, "characters"] = [c["name"] for c in data["character_credits"]]
        issues_df.at[row.Index, "description"] = data["description"]
        issues_df.at[row.Index, "image_url"] = data["image"]["medium_url"]
        issues_df.at[row.Index, "objects"] = [o["name"] for o in data["object_credits"]]
        issues_df.at[row.Index, "colorists"] = [p["name"] for p in persons if "colorist" in p.get("role", "")]
        issues_df.at[row.Index, "artists"] = [p["name"] for p in persons if "artist" in p.get("role", "")]
        issues_df.at[row.Index, "writers"] = [p["name"] for p in persons if "writer" in p.get("role", "")]
        issues_df.at[row.Index, "store_date"] = data["store_date"]
        issues_df.at[row.Index, "volume_id"] = int(data["volume"]["id"])

        time.sleep(SLEEP)

    for col in ["characters", "objects", "colorists", "artists", "writers"]:
        issues_df[col] = issues_df[col].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)

    return issues_df


def main():
    raw_volumes = fetch_volumes(API_KEY)
    volumes_df = filter_volumes(raw_volumes)
    issues_df = fetch_issues_for_volumes(volumes_df, API_KEY)
    issues_df = fetch_issue_details(issues_df, API_KEY)

    volumes_df.to_csv("all_volumes.csv", index=False)
    issues_df.to_csv("all_issues.csv", index=False)


if __name__ == "__main__":
    main()
