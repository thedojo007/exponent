"""
jarvis_energy_report.py

Reads today's sleep signal from the "Daily Log" list and scores it,
emails the result. Reads sleep data from a real checklist item if present,
falling back to a plain-text "Sleep - sleep6:y rested:y strenuous:n" line
in the task description if not (current Morning Thunder behavior, mirrors
into description rather than creating a checklist item — see 8/22 diagnosis).

Task-completion stats (STATUS section) still require actual checklist
items and will read as 0/0 with a flag when none exist — that data source
has had a separate, unrelated gap since 8/18 and is not fixed by this
patch.

Advice generation (Claude call) was cut 8/22 — redundant with Gate One
Gus (energy → action) and Morning Thunder (briefing). See Graveyard Log.

Run manually for now:
    python jarvis_energy_report.py

Deliberately NOT included yet (see phased plan):
- SMS delivery (needs Twilio account — week 2)
- Charting over time (needs multiple days of scores first — week 2)
- Cloud/unattended scheduling: added local Task Scheduler automation to
  reduce friction on daily validation runs. SMS delivery and charting
  still deferred (week 2).
"""

import os
import re
import smtplib
from collections import defaultdict
from datetime import datetime
from email.mime.text import MIMEText

from dotenv import load_dotenv

from jarvis_clickup_strategy import (
    find_list,
    get_list_tasks,
    _api_get,
    API_V2,
)

from pathlib import Path
load_dotenv(Path(__file__).resolve().parent / ".env")

DAILY_LOG_LIST_NAME = "Daily Log"


def find_daily_log_task(api_key: str, date_str: str | None = None) -> dict | None:
    """Find today's (or a given date's) task in Daily Log by exact title match."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    clickup_list = find_list(api_key, DAILY_LOG_LIST_NAME)
    tasks = get_list_tasks(api_key, clickup_list["id"])

    for task in tasks:
        if task.get("name") == date_str:
            return task
    return None


def parse_category(item_name: str) -> str:
    """Item text format: '[title] — [category] — [due status]'."""
    parts = item_name.split(" — ")
    if len(parts) >= 2:
        return parts[1].strip()
    return "Other"


def parse_sleep_data(items: list[dict]) -> dict | None:
    """Sleep data from a real checklist item (legacy Ops Odin behavior)."""
    for item in items:
        name = item.get("name", "")
        if name.startswith("Sleep - "):
            match = re.search(
                r"sleep6:(y|n|u)\s+rested:(y|n|u)\s+strenuous:(y|n|u)", name
            )
            if match:
                def to_bool(v):
                    return None if v == "u" else v == "y"
                return {
                    "slept_6plus": to_bool(match.group(1)),
                    "rested": to_bool(match.group(2)),
                    "strenuous_prior_day": to_bool(match.group(3)),
                }
    return None


def parse_sleep_data_from_text(text: str) -> dict | None:
    """Fallback: sleep line written as free text in the task description
    (current Morning Thunder mirror behavior, since ~8/18)."""
    match = re.search(
        r"Sleep - sleep6:(y|n|u)\s+rested:(y|n|u)\s+strenuous:(y|n|u)", text
    )
    if not match:
        return None

    def to_bool(v):
        return None if v == "u" else v == "y"

    return {
        "slept_6plus": to_bool(match.group(1)),
        "rested": to_bool(match.group(2)),
        "strenuous_prior_day": to_bool(match.group(3)),
    }


def compute_task_stats(task_items: list[dict]) -> dict:
    total = len(task_items)
    completed = sum(1 for i in task_items if i.get("resolved"))
    carried_over = total - completed
    completion_rate = completed / total if total else 0.0

    category_breakdown = defaultdict(lambda: {"completed": 0, "total": 0})
    for item in task_items:
        cat = parse_category(item.get("name", ""))
        category_breakdown[cat]["total"] += 1
        if item.get("resolved"):
            category_breakdown[cat]["completed"] += 1

    return {
        "completed": completed,
        "carried_over": carried_over,
        "total": total,
        "completion_rate": round(completion_rate, 2),
        "category_breakdown": dict(category_breakdown),
    }


def compute_sleep_score_from_data(sleep_data: dict | None) -> dict:
    """Energy score, 0-10, derived ONLY from sleep/rest/strenuousness.
    Task completion is a separate axis and never enters this number."""
    if sleep_data is None:
        return {"score": None, "slept_6plus": None, "rested": None, "strenuous_prior_day": None}

    known = [v for v in sleep_data.values() if v is not None]
    if not known:
        return {"score": None, **sleep_data}

    raw = 0.0
    if sleep_data["slept_6plus"] is True:
        raw += 5
    if sleep_data["rested"] is True:
        raw += 5
    if sleep_data["strenuous_prior_day"] is True:
        raw = max(0.0, raw - 2)

    core_known = len([v for v in [sleep_data["slept_6plus"], sleep_data["rested"]] if v is not None])
    raw *= core_known / 2  # partial confidence if a core signal is missing

    return {"score": round(raw, 1), **sleep_data}


def compute_daily_report(api_key: str, date_str: str | None = None) -> dict:
    task = find_daily_log_task(api_key, date_str)
    if task is None:
        return {"has_data": False, "note": "No Daily Log entry for this date — check Morning Thunder ran today."}

    full_task = _api_get(api_key, API_V2, f"/task/{task['id']}")
    items = []
    for checklist in full_task.get("checklists", []):
        items.extend(checklist.get("items", []))

    description = full_task.get("text_content") or full_task.get("description") or ""
    sleep_data = parse_sleep_data(items) or parse_sleep_data_from_text(description)

    if not items and sleep_data is None:
        return {"has_data": False, "note": "Today's Daily Log entry has no checklist items and no sleep line yet."}

    task_items = [i for i in items if parse_category(i.get("name", "")) != "Sleep"]
    stats = compute_task_stats(task_items)
    if not items:
        stats["no_checklist_data"] = True

    score = compute_sleep_score_from_data(sleep_data)
    return {"has_data": True, **stats, **score}


def format_category_breakdown(breakdown: dict) -> str:
    lines = []
    for cat, counts in sorted(breakdown.items()):
        lines.append(f"  {cat}: {counts['completed']}/{counts['total']}")
    return "\n".join(lines)


def send_email(subject: str, body: str) -> None:
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_APP_PASSWORD")
    to_email = os.getenv("REPORT_TO_EMAIL", smtp_user)

    if not smtp_user or not smtp_pass:
        raise SystemExit("SMTP_USER / SMTP_APP_PASSWORD not set in .env")

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_email], msg.as_string())


OUTSTANDING_LIST_ID = os.getenv("OUTSTANDING_LIST_ID")


def get_professional_outcomes_updates(api_key: str, since_datetime=None) -> list[dict]:
    tasks = get_list_tasks(api_key, OUTSTANDING_LIST_ID)
    if since_datetime is None:
        return tasks
    since_ms = int(since_datetime.timestamp() * 1000)
    return [t for t in tasks if int(t.get("date_updated", 0)) >= since_ms]


def main() -> None:
    clickup_key = os.getenv("CLICKUP_API_KEY")
    if not clickup_key:
        raise SystemExit("CLICKUP_API_KEY must be set")

    today = datetime.now().strftime("%Y-%m-%d")
    report = compute_daily_report(clickup_key)

    if not report["has_data"]:
        body = report["note"]
        subject = f"Jarvis daily report — {today} — no data yet"
        print(body)
        send_email(subject, body)
        print("\nSent.")
        return

    if report.get("no_checklist_data"):
        status_section = "STATUS\nNo checklist data since ~8/18 (Morning Thunder writes to description, not checklist)."
    else:
        breakdown_str = format_category_breakdown(report["category_breakdown"])
        status_section = (
            f"STATUS\n"
            f"Completed: {report['completed']}/{report['total']} "
            f"({report['carried_over']} carried over)\n\n"
            f"By category:\n{breakdown_str}"
        )

    if report["score"] is not None:
        energy_section = (
            f"ENERGY: {report['score']}/10\n"
            f"Sleep >6hrs: {report['slept_6plus']} | Rested: {report['rested']} "
            f"| Strenuous prior day: {report['strenuous_prior_day']}"
        )
    else:
        energy_section = "ENERGY: no sleep data logged today"

    body = f"{status_section}\n\n{energy_section}"
    subject_score = f"{report['score']}/10" if report["score"] is not None else "no energy data"
    subject = f"Jarvis daily report — {today} — energy {subject_score}"

    print(body)
    send_email(subject, body)
    print("\nSent.")

    po_updates = get_professional_outcomes_updates(clickup_key)
    print(f"\nProfessional Outcomes tasks: {len(po_updates)}")


if __name__ == "__main__":
    main()