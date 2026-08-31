"""
Session-to-Task pipeline (v2, single-bucket + dedup)
Parses a session recap's "Open Loops" bucket into discrete task title strings,
then writes them via a confirm-gated live write to a ClickUp list. Before
writing, checks candidate titles against existing tasks in the target list
and skips exact duplicates.

Scope (Principle 5 - module isolation): separate file from jarvis_session_sync.py
on purpose -- that script's job is session.txt -> ClickUp Doc pages (append,
hash-deduped). This script's job is bucket text -> ClickUp tasks (create,
title-matched). Different target entity, different write semantics -- kept
apart so a bug in one write path can't touch the other.

Reuses jarvis_session_sync.py's auth/retry plumbing rather than duplicating it
(via negativa -- one retry implementation, not two).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_session_sync import _request_with_retry, _normalize, API_KEY, WORKSPACE_ID  # noqa: E402


def parse_open_loops(text: str) -> list[str]:
    """Session 'Open Loops' bucket text -> task title strings. Line-based, no AI judgment call."""
    tasks = []
    for line in text.strip().split("\n"):
        line = line.strip().lstrip("-*•").strip()
        if line:
            tasks.append(line)
    return tasks


def dry_run_task_creation(task_titles: list[str], list_name: str = "Build Log") -> list[str]:
    print(f"[DRY RUN] Would create {len(task_titles)} task(s) in {list_name}:")
    for t in task_titles:
        print(f"  - {t}")
    return task_titles


def _create_clickup_task(task_name: str, list_id: str, status: str, api_key: str) -> dict:
    """Single isolated network call, via jarvis_session_sync's retry wrapper.
    Not called directly -- go through confirm_and_write."""
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    resp = _request_with_retry(
        "POST",
        f"https://api.clickup.com/api/v2/list/{list_id}/task",
        headers,
        json={"name": task_name, "status": status},
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_existing_task_titles(list_id: str, api_key: str) -> set[str]:
    """GET all tasks (open + closed) in list_id, return normalized titles.
    Read-only -- no confirmation gate needed (Principle 8 only guards writes)."""
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    titles: set[str] = set()
    page = 0
    while True:
        resp = _request_with_retry(
            "GET",
            f"https://api.clickup.com/api/v2/list/{list_id}/task",
            headers,
            params={"include_closed": "true", "page": page},
        )
        resp.raise_for_status()
        data = resp.json()
        tasks = data.get("tasks", [])
        if not tasks:
            break
        titles.update(_normalize(t["name"]) for t in tasks)
        if data.get("last_page", True):
            break
        page += 1
    return titles


def dedup_task_titles(task_titles: list[str], list_id: str, api_key: str) -> tuple[list[str], list[str]]:
    """Split candidate titles into (new, skipped_as_duplicate) via exact
    normalized-title match against existing tasks in list_id.

    Deliberately exact-match only, not fuzzy/substring -- a false-positive
    skip silently drops a real task with no record it was ever considered,
    which is worse than a false-negative duplicate (which just shows up
    for human review in the normal confirm_and_write dry run). Anything
    short of an exact match falls through to the human via the existing
    confirm gate rather than getting an automatic decision (Principle 8).

    Known gap: _normalize does not lowercase, so a title differing only
    by case will NOT be caught as a duplicate. Left as-is deliberately --
    fixing it is a separate, small follow-up, not bundled in here.
    """
    existing = _fetch_existing_task_titles(list_id, api_key)
    new, skipped = [], []
    for title in task_titles:
        (skipped if _normalize(title) in existing else new).append(title)
    return new, skipped


def confirm_and_write(
    task_titles: list[str],
    list_id: str,
    status: str = "scoping",
    api_key: str | None = None,
) -> list[str]:
    """
    Principle 8 gate: shows the dry run, requires explicit 'y' before any write.
    Returns list of created task IDs (empty if declined or on failure).
    """
    key = api_key or API_KEY
    if key:
        task_titles, skipped = dedup_task_titles(task_titles, list_id, key)
        if skipped:
            print(f"[DEDUP] Skipping {len(skipped)} title(s) already in list {list_id}:")
            for t in skipped:
                print(f"  - {t}")
        if not task_titles:
            print("[DONE] Nothing new to write -- all candidates were duplicates.")
            return []

    dry_run_task_creation(task_titles, list_name=f"list {list_id}")

    confirm = input(f"\nCreate these {len(task_titles)} task(s) in ClickUp status='{status}'? [y/N]: ").strip().lower()
    if confirm != "y":
        print("[ABORTED] No tasks written.")
        return []

    key = api_key or API_KEY
    if not key:
        print("[ERROR] No CLICKUP_API_KEY set (.env or api_key arg). Nothing written.")
        return []

    created_ids = []
    for title in task_titles:
        try:
            result = _create_clickup_task(title, list_id, status, key)
            created_ids.append(result["id"])
            print(f"  [OK] {title} -> {result['id']}")
        except Exception as e:
            print(f"  [FAIL] {title} -> {e}")

    print(f"\n[DONE] {len(created_ids)}/{len(task_titles)} tasks written.")
    return created_ids


if __name__ == "__main__":
    test_input = """Fix task_summary in jarvis_next_steps.py to send task descriptions, not just names
Recon empty-bracket citation formatting bug
Threshold Theo: live test (3-meeting) pending before Build Log entry
jarvis_energy_report.py full deprecation — unmerged on cursor/deprecate-energy-report-42b8
Standing end-session protocol for task closure signal — scripting deferred
parse_buckets() in jarvis_session_sync.py — substring-matching fragility, needs line-anchored regex"""

    parsed = parse_open_loops(test_input)
    assert len(parsed) == 6, f"FAIL: expected 6 tasks, got {len(parsed)}"
    assert parsed[0] == "Fix task_summary in jarvis_next_steps.py to send task descriptions, not just names"
    assert all(t and not t.startswith(("-", "*", "•")) for t in parsed), "FAIL: bullet stripping broken"

    confirm_and_write(parsed[:1], list_id="901715560513", status="scoping")