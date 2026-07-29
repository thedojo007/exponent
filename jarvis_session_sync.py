# jarvis_session_sync.py
import sys, json, os, re, time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')

API_KEY = os.getenv("CLICKUP_API_KEY")
WORKSPACE_ID = os.getenv("CLICKUP_WORKSPACE_ID")
# jarvis_session_sync.py 상단부, DRY_RUN 정의 아래에 추가/교체
DRY_RUN = "--dry-run" in sys.argv

SESSION_FILE = Path(__file__).resolve().parent / "session.txt"

BUCKET_HEADERS = [
    "Jarvis: Vision & Philosophy",
    "Jarvis: Agent Spec",
    "Jarvis: ClickUp Setup Notes",
    "Jarvis: Build Log",
    "Jarvis: Product & Monetization",
    "Jarvis State File",
    "Jarvis 15%",
]

with open(Path(__file__).resolve().parent / "page_id.json", encoding="utf-8") as f:
    page_map = json.load(f)
    # Expected new format:
    # {
    #   "Jarvis: Vision & Philosophy": {"doc_id": "...", "page_id": "..."},
    #   "Jarvis: Agent Spec": {"doc_id": "...", "page_id": "..."},
    #   ...
    # }


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

    for attempt in range(3):
        current = requests.get(base, headers=headers, params={"content_format": "text/md"})
        if current.status_code == 200:
            break
        time.sleep(2)
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
    if not API_KEY or not WORKSPACE_ID:
        print("[ERROR] Missing CLICKUP_API_KEY or CLICKUP_WORKSPACE_ID in .env")
        sys.exit(1)

    text = SESSION_FILE.read_text(encoding="utf-8")
    buckets = parse_buckets(text)

    if not buckets:
        print("[WARN] No recognized bucket headers found in input. Nothing to sync.")
        return

    for header, content in buckets.items():
        entry = page_map.get(header)
        if not entry or not entry.get("doc_id") or not entry.get("page_id"):
            print(f"[SKIP] No doc_id/page_id mapped for bucket: {header}")
            continue

        if DRY_RUN:
            print(f"[DRY RUN] Would append to {header} (doc {entry['doc_id']}, page {entry['page_id']}):\n{content}\n{'-'*40}")
        else:
            append_to_page(WORKSPACE_ID, entry["doc_id"], entry["page_id"], content, API_KEY)
            print(f"[OK] Synced (append): {header}")


if __name__ == "__main__":
    main()