import requests
from dotenv import load_dotenv
import os
import json
import pandas as pd
import time

load_dotenv()

API_KEY = os.getenv("API_KEY")
BASE_URL = "https://comicvine.gamespot.com/api/"
endpoint = "volumes/"
url = BASE_URL + endpoint

headers = {
    "User-Agent": "absolutePipeline"  
}

all_results = []
offset = 0
limit = 100
api_calls= 0
SLEEP = 1

while True:
  params = {
        "api_key": API_KEY,
          "format": "json", 
          "filter": "name:Absolute",
          "limit" : limit,
          "offset" : offset
  }

  response = requests.get(url=url, params=params, headers=headers)
  data = response.json()
  api_calls += 1
  print(f"api calls: {api_calls}")

  results = data['results']
  all_results.extend(results)

  print(f"Fetched {len(results)} records. Total: {len(all_results)}")

  if len(all_results) >= data["number_of_total_results"]:
    break

  offset += limit

print(f"Final count: {len(all_results)}")

volumes = pd.json_normalize(all_results, sep="_")

volumes["start_year"] = volumes["start_year"].astype(int)
volumes = volumes[volumes["start_year"]>=2024]
volumes = volumes[volumes["publisher_name"] == "DC Comics"]
volumes = volumes[~volumes["name"].str.contains("Absolute Power", na=False)]

volumes = volumes[['api_detail_url', 'count_of_issues', 'date_added','date_last_updated', 'description', 'id', 'name','site_detail_url', 'start_year', 'first_issue_api_detail_url','first_issue_id', 'first_issue_name', 'first_issue_issue_number','image_medium_url','last_issue_api_detail_url', 'last_issue_id','last_issue_name', 'last_issue_issue_number','publisher_api_detail_url', 'publisher_id', 'publisher_name']]

params = {
        "api_key": API_KEY,
        "format": "json", 
        "field_list": "issues"
}

all_issues_df = pd.DataFrame(columns=["api_detail_url",	"id",	"name",	"site_detail_url",	"issue_number"])

for row in volumes.itertuples(): 
    print(f"{row.Index} getting issues of {row.name} at {row.api_detail_url}...")
    volume_api_url = row.api_detail_url
    response = requests.get(url=volume_api_url, params=params, headers=headers)
    data= response.json()
    api_calls += 1
    print(f"api calls: {api_calls}")
    issues = data["results"]["issues"]
    issues_df = pd.DataFrame(issues)
    all_issues_df = pd.concat([all_issues_df, issues_df], ignore_index=True)
    time.sleep(SLEEP)

params = {
        "api_key": API_KEY,
        "format": "json", 
        "field_list": ["date_last_updated,character_credits,description,id,image,object_credits,person_credits,store_date,volume"]
}


for col in ["characters", "objects", "colorists", "artists", "writers"]:
    all_issues_df[col] = None
for row in all_issues_df.itertuples():
    print(f"{row.Index} getting data of issue {row.name} at {row.api_detail_url}...")
    issue_url = all_issues_df['api_detail_url'][row.Index]

    response = requests.get(url=issue_url, params=params, headers=headers)
    data = response.json()
    api_calls += 1
    print(f"api calls: {api_calls}")

    characters_json = data["results"]["character_credits"]
    characters_list = []
    for character in characters_json: 
        characters_list.append(character.get("name"))

    description= data["results"]["description"]

    image_url = data["results"]["image"]["medium_url"]

    objects_json = data["results"]["object_credits"]
    objects_list = []
    for object in objects_json: 
        objects_list.append(object.get("name"))
   
    persons_json = data["results"]["person_credits"] 
    for person in persons_json: 
        colorists = [p["name"] for p in persons_json if "colorist" in p.get("role", "")]
        artists = [p["name"] for p in persons_json if "artist" in p.get("role", "")]
        writers = [p["name"] for p in persons_json if "writer" in p.get("role", "")]
    
    store_date = data["results"]["store_date"] 
    volume_id = data["results"]["volume"]["id"]

    all_issues_df.at[row.Index, "characters"] = characters_list
    all_issues_df.at[row.Index, "description"] = description
    all_issues_df.at[row.Index, "image_url"] = image_url
    all_issues_df.at[row.Index, "objects"] = objects_list
    all_issues_df.at[row.Index, "colorists"] = colorists
    all_issues_df.at[row.Index, "artists"] = artists
    all_issues_df.at[row.Index, "writers"] = writers
    all_issues_df.at[row.Index, "store_date"] = store_date
    all_issues_df.at[row.Index, "volume_id"] = int(volume_id)

    time.sleep(SLEEP)

for col in ["characters", "objects", "colorists", "artists", "writers"]:
    all_issues_df[col] = all_issues_df[col].apply(
        lambda x: ", ".join(x) if isinstance(x, list) else x
    )

volumes.to_csv("all_volumes.csv")
all_issues_df.to_csv("all_issues.csv")