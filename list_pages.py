# list_pages.py
import os, json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

API_KEY = os.getenv("CLICKUP_API_KEY")
WORKSPACE_ID = os.getenv("CLICKUP_WORKSPACE_ID")
DOC_ID = os.getenv("CLICKUP_DOC_ID")

if not API_KEY or not WORKSPACE_ID or not DOC_ID:
    print("[ERROR] Missing CLICKUP_API_KEY, CLICKUP_WORKSPACE_ID, or CLICKUP_DOC_ID in .env")
    exit(1)

url = f"https://api.clickup.com/api/v3/workspaces/{WORKSPACE_ID}/docs/{DOC_ID}/pages"
headers = {"Authorization": API_KEY, "Content-Type": "application/json"}

resp = requests.get(url, headers=headers)

if resp.status_code != 200:
    print(f"[ERROR] {resp.status_code}: {resp.text}")
    print("\nIf this is a 404, CLICKUP_DOC_ID is likely wrong — double check it against a page's actual parent doc, not just the URL segment you assumed.")
    exit(1)

pages = resp.json()

# API may return a list directly, or a dict wrapping a list — handle both
if isinstance(pages, dict):
    pages = pages.get("pages", pages)

print(f"Found {len(pages)} page(s) under doc {DOC_ID}:\n")

def walk(page_list, indent=0):
    for p in page_list:
        name = p.get("name", "(unnamed)")
        page_id = p.get("id", "(no id)")
        print(f"{'  ' * indent}{name}  →  {page_id}")
        children = p.get("pages") or p.get("subpages") or []
        if children:
            walk(children, indent + 1)

walk(pages)