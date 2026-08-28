# jarvis_next_steps.py
#
# Session start: rebuild next_steps.md from the live Build Log +
# Components task lists (grouped by Context), append a Top 3 priority
# recommendation grounded in the Guidelines v.2 (What Works/Doesn't)
# doc, and overwrite the Jarvis: Next Steps ClickUp doc. Full rewrite,
# not an append. Run this when you sit down, not at close-out.
#
#   python jarvis_next_steps.py
#   python jarvis_next_steps.py --dry-run
#
import sys, os
import json
from pathlib import Path

from dotenv import load_dotenv
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_session_sync as jss

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

OUTPUT_FILE = Path(__file__).resolve().parent / "next_steps.md"
DRY_RUN = "--dry-run" in sys.argv

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

BUILD_LOG_LIST_ID = "901715560513"   # confirmed live, 8/16
COMPONENTS_LIST_ID = "901715560511"  # confirmed live, 8/16

NEXT_STEPS_BUCKET = "Jarvis: Next Steps"
WHAT_WORKS_BUCKET = "Guidelines v.2"  # confirmed correct, 8/16

CONTEXT_ORDER = ["Work-Automation", "Personal", "15%-Career", "(unset)"]


# ---------- Module 1: task retrieval + grouping ----------

def fetch_list_tasks(list_id: str, api_key: str) -> list[dict]:
    """GET all tasks in a list, including closed ones -- closed status
    is needed to distinguish them, but callers must filter before use."""
    url = f"https://api.clickup.com/api/v2/list/{list_id}/task"
    headers = {"Authorization": api_key}
    params = {"include_closed": "true"}
    resp = jss._request_with_retry("GET", url, headers, params=params)
    resp.raise_for_status()
    return resp.json().get("tasks", [])

EXCLUDED_STATUSES = {"in review"}  # extend later if other statuses need excluding

def is_open(task: dict) -> bool:
    status = task.get("status", {})
    status_type = status.get("type", "")
    status_name = status.get("status", "").strip().lower()
    if status_type in ("closed", "done"):
        return False
    if status_name in EXCLUDED_STATUSES:
        return False
    return True

def get_context_field(task: dict) -> str:
    """Dropdown custom fields return 'value' as an index into
    type_config.options, not the label -- has to be resolved."""
    for cf in task.get("custom_fields", []):
        if cf.get("name") == "Context":
            value = cf.get("value")
            if value is None:
                return "(unset)"
            for opt in cf.get("type_config", {}).get("options", []):
                if opt.get("orderindex") == value:
                    return opt.get("name", "(unknown option)")
            return f"(unresolved index: {value})"
    return "(no Context field)"


def build_task_section(tasks: list[dict]) -> str:
    open_tasks = [t for t in tasks if is_open(t)]
    lines = [f"## Open Tasks by Context ({len(open_tasks)} open, {len(tasks) - len(open_tasks)} closed hidden)", ""]
    by_context: dict[str, list[dict]] = {}
    for t in open_tasks:
        by_context.setdefault(get_context_field(t), []).append(t)

    ordered_keys = [k for k in CONTEXT_ORDER if k in by_context] + \
                   [k for k in by_context if k not in CONTEXT_ORDER]

    for context in ordered_keys:
        lines.append(f"### {context}")
        for t in by_context[context]:
            lines.append(f"- {t.get('name')}")
        lines.append("")

    return "\n".join(lines)


# ---------- Module 2: priority synthesis (isolated -- can fail without breaking Module 1) ----------

def fetch_what_works(page_map: dict) -> str | None:
    entry = page_map.get(WHAT_WORKS_BUCKET)
    if not entry or not entry.get("doc_id") or not entry.get("page_id"):
        return None
    return jss.fetch_page_content(jss.WORKSPACE_ID, entry["doc_id"], entry["page_id"], jss.API_KEY)

def call_claude(task_summary: str, what_works_content: str) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    prompt = f"""Here is my open task list (Build Log + Components), already
filtered to exclude closed/completed items:

{task_summary}

Pick exactly 3 tasks to prioritize today, using these standards in order:
1. Closest to shipping -- tasks already in progress, mid-validation, or one
   small step from done beat fresh starts.
2. Unblocks other work -- a task that other backlog items depend on beats
   an isolated one.
3. Closes an open loop -- fixes a flagged bug, resolves a known drift, or
   finishes something explicitly left unconfirmed.

Constraint: at least one of the three must be small enough to finish in a
single sitting (a bounded win, not a multi-session build) -- use this
reference sheet only to judge which candidate qualifies as that small win,
not to justify the other two picks:

{what_works_content}

State each rationale plainly and specifically, tied to which standard above
drove the pick. Do not hedge or note that a pick is "a stretch" -- if a
task doesn't clearly satisfy one of the three standards, don't pick it.
Output as:
1. [task name] -- [rationale]
2. [task name] -- [rationale]
3. [task name] -- [rationale]
"""
    body = {
        "model": "claude-sonnet-5",
        "max_tokens": 1000,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")

def build_priority_section(tasks: list[dict], page_map: dict) -> str:
    open_tasks = [t for t in tasks if is_open(t)]
    lines = ["## Today's Top 3 (suggestion only -- nothing written to ClickUp)", ""]

    if not ANTHROPIC_API_KEY:
        print("[DEBUG] ANTHROPIC_API_KEY missing")
        lines.append("_Skipped: ANTHROPIC_API_KEY not set in .env._")
        return "\n".join(lines)

    what_works = fetch_what_works(page_map)
    print(f"[DEBUG] what_works fetch returned: {repr(what_works)[:200]}")
    if what_works is None:
        lines.append(f"_Skipped: no page_id.json entry for '{WHAT_WORKS_BUCKET}'._")
        return "\n".join(lines)

    task_summary = "\n".join(f"- [{get_context_field(t)}] {t.get('name')}" for t in open_tasks)

    try:
        result = call_claude(task_summary, what_works)
        print(f"[DEBUG] call_claude returned: {repr(result)[:200]}")
        lines.append(result)
    except requests.exceptions.RequestException as e:
        print(f"[DEBUG] call_claude raised: {e}")
        lines.append(f"_Skipped: Anthropic API call failed ({e})._")

    return "\n".join(lines)


# ---------- Orchestration ----------

def build_markdown(tasks: list[dict], page_map: dict) -> str:
    header = [
        "# Jarvis Next Steps",
        "",
        "Fully rewritten from scratch every run, not appended to --",
        "nothing here is permanent, don't build on top of it by hand.",
        "",
        f"_{len(tasks)} tasks scanned (Build Log + Components)._",
        "",
    ]
    return "\n".join(header) + "\n" + build_priority_section(tasks, page_map) + "\n\n" + build_task_section(tasks)


def main():
    if not jss.API_KEY or not jss.WORKSPACE_ID:
        print("[ERROR] Missing CLICKUP_API_KEY or CLICKUP_WORKSPACE_ID in .env")
        sys.exit(1)

    page_map = jss.load_page_map()

    tasks = fetch_list_tasks(BUILD_LOG_LIST_ID, jss.API_KEY) + \
            fetch_list_tasks(COMPONENTS_LIST_ID, jss.API_KEY)
    markdown = build_markdown(tasks, page_map)

    OUTPUT_FILE.write_text(markdown, encoding="utf-8")
    print(f"[OK] Wrote {len(tasks)} tasks + priority section to {OUTPUT_FILE}")

    next_steps_entry = page_map.get(NEXT_STEPS_BUCKET)
    if not next_steps_entry or not next_steps_entry.get("doc_id") or not next_steps_entry.get("page_id"):
        print(f"[SKIP] No page_id.json entry for '{NEXT_STEPS_BUCKET}' yet.")
        return

    if DRY_RUN:
        print(f"[DRY RUN] Would overwrite ClickUp doc '{NEXT_STEPS_BUCKET}'")
        return

    jss.write_page_content(jss.WORKSPACE_ID, next_steps_entry["doc_id"], next_steps_entry["page_id"], markdown, jss.API_KEY)
    print(f"[OK] Overwrote ClickUp doc '{NEXT_STEPS_BUCKET}' from scratch")


if __name__ == "__main__":
    main()