# jarvis_session_sync.py
import sys, json, os, re
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')


API_KEY = os.getenv("CLICKUP_API_KEY")
WORKSPACE_ID = os.getenv("CLICKUP_WORKSPACE_ID")
DOC_ID = os.getenv("CLICKUP_DOC_ID")
DRY_RUN = "--dry-run" in sys.argv

BUCKET_HEADERS = [
    "Jarvis: Vision & Philosophy",
    "Jarvis: Agent Spec",
    "Jarvis: ClickUp Setup Notes",
    "Jarvis: Build Log",
    "Jarvis: Product & Monetization",
    "Jarvis State File",
    "Jarvis 15%",
]

with open(Path(__file__).resolve().parent / "page_id.json") as f:
    page_map = json.load(f)


def parse_buckets(text: str) -> dict[str, str]:
    pattern = "|".join(re.escape(h) for h in BUCKET_HEADERS)
    splits = re.split(f"({pattern})", text)
    buckets = {}
    for i in range(1, len(splits), 2):
        header = splits[i].strip()
        content = splits[i + 1].strip()
        if content:
            buckets[header] = content
    return buckets


def append_to_page(workspace_id, doc_id, page_id, new_content, api_key):
    base = f"https://api.clickup.com/api/v3/workspaces/{workspace_id}/docs/{doc_id}/pages/{page_id}"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}

    current = requests.get(base, headers=headers)
    current.raise_for_status()
    existing_content = current.json().get("content", "")
    updated_content = existing_content + "\n\n" + new_content

    resp = requests.put(base, headers=headers, json={"content": updated_content})
    resp.raise_for_status()

    if resp.text.strip():
        try:
            return resp.json()
        except requests.exceptions.JSONDecodeError:
            return {"status": "ok (non-JSON response)", "raw": resp.text}
    return {"status": "ok (empty response)"}


def main():
    if not API_KEY or not WORKSPACE_ID or not DOC_ID:
        print("[ERROR] Missing CLICKUP_API_KEY, CLICKUP_WORKSPACE_ID, or CLICKUP_DOC_ID in .env")
        sys.exit(1)

    text = sys.stdin.read()
    buckets = parse_buckets(text)

    if not buckets:
        print("[WARN] No recognized bucket headers found in input. Nothing to sync.")
        return

    for header, content in buckets.items():
        page_id = page_map.get(header)
        if not page_id:
            print(f"[SKIP] No page_id mapped for bucket: {header}")
            continue

        if DRY_RUN:
            print(f"[DRY RUN] Would append to {header} (page {page_id}):\n{content}\n{'-'*40}")
        else:
            append_to_page(WORKSPACE_ID, DOC_ID, page_id, content, API_KEY)
            print(f"[OK] Synced (append): {header}")


if __name__ == "__main__":
    main()