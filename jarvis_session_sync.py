# jarvis_session_sync.py
#
# Session close-out: append session.txt buckets to mapped ClickUp Docs.
#
#   python jarvis_session_sync.py
#   python jarvis_session_sync.py --dry-run
#
import sys, json, os, re, time, hashlib
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')

API_KEY = os.getenv("CLICKUP_API_KEY")
WORKSPACE_ID = os.getenv("CLICKUP_WORKSPACE_ID")
DRY_RUN = "--dry-run" in sys.argv

SESSION_FILE = Path(__file__).resolve().parent / "session.txt"
PAGE_ID_FILE = Path(__file__).resolve().parent / "page_id.json"
# Records which (bucket, content) pairs have already been successfully
# synced, so re-running the same session.txt (retry after a partial
# failure, or just running it twice by habit) is a no-op instead of a
# duplicate append. Keyed by header -> hash of the content that was sent.
SYNC_STATE_FILE = Path(__file__).resolve().parent / ".sync_state.json"

BUCKET_HEADERS = [
    "Jarvis: Vision & Philosophy",
    "Jarvis: Agent Spec",
    "Jarvis: ClickUp Setup Notes",
    "Jarvis: Build Log",
    "Jarvis: Product & Monetization",
    "Jarvis State File",
    "Jarvis 15%",
    "Jarvis: Graveyard Log",
]


def load_page_map():
    if not PAGE_ID_FILE.exists():
        print(f"[ERROR] {PAGE_ID_FILE} not found. Nothing to sync against.")
        sys.exit(1)
    try:
        with open(PAGE_ID_FILE, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERROR] {PAGE_ID_FILE} is not valid JSON: {e}")
        sys.exit(1)


def load_sync_state():
    if SYNC_STATE_FILE.exists():
        try:
            with open(SYNC_STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            # Corrupt state file shouldn't block syncing -- worst case is
            # one redundant append, which is recoverable by hand. Missing
            # protection entirely (crashing) is worse.
            print(f"[WARN] {SYNC_STATE_FILE} is corrupt, ignoring it this run.")
            return {}
    return {}


def save_sync_state(state):
    with open(SYNC_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _request_with_retry(method, url, headers, attempts=3, backoff=2, **kwargs):
    """GET or PUT with retry that actually catches connection failures,
    not just bad status codes, and backs off between attempts."""
    last_exc = None
    for attempt in range(attempts):
        try:
            resp = requests.request(method, url, headers=headers, timeout=15, **kwargs)
            if resp.status_code < 500:
                # Any non-5xx response (200, or a real 4xx client error) is
                # final -- retrying a 401/404 just wastes time and delays
                # the real error. Only 5xx/connection failures are retried.
                return resp
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exc = e
        if attempt < attempts - 1:
            time.sleep(backoff * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    return resp  # last 5xx response, let raise_for_status surface it


def _normalize(text: str) -> str:
    # ClickUp's content_format=text/md round-trip backslash-escapes
    # markdown-special characters on GET (notably underscores, since _
    # is italics syntax) even though what was PUT had none. Any
    # filename or identifier with an underscore (jarvis_session_sync.py,
    # task_easer.py, ...) would silently fail the duplicate check
    # without this -- confirmed via diagnose_sync_mismatch.py, not a
    # guess. Un-escape those, then collapse whitespace.
    text = re.sub(r"\\([_*\[\]()#+\-.!`~])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_page_content(workspace_id, doc_id, page_id, api_key):
    base = f"https://api.clickup.com/api/v3/workspaces/{workspace_id}/docs/{doc_id}/pages/{page_id}"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    resp = _request_with_retry("GET", base, headers, params={"content_format": "text/md"})
    resp.raise_for_status()
    return resp.json().get("content", "")


def write_page_content(workspace_id, doc_id, page_id, updated_content, api_key):
    base = f"https://api.clickup.com/api/v3/workspaces/{workspace_id}/docs/{doc_id}/pages/{page_id}"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    resp = _request_with_retry("PUT", base, headers, json={"content": updated_content})
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

    if not SESSION_FILE.exists():
        print(f"[ERROR] {SESSION_FILE} not found. Paste the session close-out content there first.")
        sys.exit(1)

    page_map = load_page_map()
    sync_state = load_sync_state()

    text = SESSION_FILE.read_text(encoding="utf-8")
    buckets = parse_buckets(text)

    if not buckets:
        print("[WARN] No recognized bucket headers found in input. Nothing to sync.")
        return

    state_changed = False

    for header, content in buckets.items():
        entry = page_map.get(header)
        if not entry or not entry.get("doc_id") or not entry.get("page_id"):
            print(f"[SKIP] No doc_id/page_id mapped for bucket: {header}")
            continue

        h = content_hash(content)

        # Fast path: local state already confirms this exact content was
        # synced. Skip without even hitting the API.
        if sync_state.get(header) == h:
            print(f"[SKIP] Already synced (local state, unchanged): {header}")
            continue

        # Local state doesn't confirm it -- either it's genuinely new, or
        # local state was lost/never existed on this machine. Either way,
        # the only source of truth that actually matters is the live page,
        # so check that before appending anything.
        existing_content = fetch_page_content(WORKSPACE_ID, entry["doc_id"], entry["page_id"], API_KEY)

        if _normalize(content) in _normalize(existing_content):
            print(f"[SKIP] Already present on the live page (local state was out of sync): {header}")
            if not DRY_RUN:
                sync_state[header] = h
                state_changed = True
            continue

        if DRY_RUN:
            print(f"[DRY RUN] Would append to {header} (doc {entry['doc_id']}, page {entry['page_id']}):\n{content}\n{'-'*40}")
            # Deliberately don't record state on a dry run -- it hasn't
            # actually been written anywhere yet.
        else:
            updated_content = (existing_content + "\n\n" + content) if existing_content else content
            write_page_content(WORKSPACE_ID, entry["doc_id"], entry["page_id"], updated_content, API_KEY)
            sync_state[header] = h
            state_changed = True
            print(f"[OK] Synced (append): {header}")

    if state_changed:
        save_sync_state(sync_state)


if __name__ == "__main__":
    main()
