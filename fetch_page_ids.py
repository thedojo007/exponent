# fetch_page_ids.py
import requests, os, json, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
api_key = os.getenv("CLICKUP_API_KEY")
workspace_id = os.getenv("CLICKUP_WORKSPACE_ID")

PAGE_ID_FILE = Path(__file__).resolve().parent / "page_id.json"

DOC_IDS = {
    "Jarvis: Vision & Philosophy": "8cqjyhy-2817",
    "Jarvis: Agent Spec": "8cqjyhy-2697",
    "Jarvis: ClickUp Setup Notes": "8cqjyhy-2777",
    "Jarvis: Build Log": "8cqjyhy-2797",
    "Jarvis: Product & Monetization": "8cqjyhy-2717",
    "Jarvis State File": "8cqjyhy-2757",
    "Jarvis: Next Steps": "8cqjyhy-3717",
    "Guidelines v.2": "8cqjyhy-757",
}
existing = {}
if PAGE_ID_FILE.exists():
    try:
        existing = json.loads(PAGE_ID_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"[WARN] {PAGE_ID_FILE} is not valid JSON; starting from an empty map.")

page_map = {}
for bucket, doc_id in DOC_IDS.items():
    url = f"https://api.clickup.com/api/v3/workspaces/{workspace_id}/docs/{doc_id}/pages"
    for attempt in range(3):
        r = requests.get(url, headers={"Authorization": api_key})
        if r.status_code == 200:
            page_id = r.json()[0]["id"]
            page_map[bucket] = {"doc_id": doc_id, "page_id": page_id}
            print(f"{bucket}: doc_id={doc_id}, page_id={page_id}")
            break
        else:
            print(f"[RETRY {attempt+1}/3] {bucket} -> {r.status_code}")
            time.sleep(2)
    else:
        print(f"[FAIL] {bucket}: could not fetch page_id after 3 attempts")

# Keep keys that DOC_IDS does not know about (e.g. a hand-added Graveyard
# mapping) so a setup re-run cannot silently drop them.
merged = {**existing, **page_map}

PAGE_ID_FILE.write_text(
    json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print(f"\n[OK] page_id.json written with {len(page_map)}/{len(DOC_IDS)} refreshed buckets, {len(merged)} total keys.")
