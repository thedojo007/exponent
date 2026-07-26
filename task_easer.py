# task_easer.py
import requests, os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
API_KEY = os.getenv("CLICKUP_API_KEY")
LIST_ID = os.getenv("TASK_EASER_LIST_ID")  # Task Easer Machine list
HEADERS = {"Authorization": API_KEY}

# priority ladder: lower number = higher urgency in ClickUp (1=Urgent...4=Low)
def ease_priority(current):
    return min((current or 3) + 1, 4)  # step down one notch, floor at Low

def get_tasks():
    url = f"https://api.clickup.com/api/v2/list/{LIST_ID}/task"
    params = {"include_closed": "false"}
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    return r.json()["tasks"]

def days_stale(task):
    updated = datetime.fromtimestamp(int(task["date_updated"]) / 1000, tz=timezone.utc)
    return (datetime.now(timezone.utc) - updated).days

def already_eased(task):
    return any(t["name"] == "eased" for t in task.get("tags", []))

def apply_ease(task):
    task_id = task["id"]
    new_priority = ease_priority(task["priority"]["id"] if task["priority"] else None)
    requests.put(
        f"https://api.clickup.com/api/v2/task/{task_id}",
        headers=HEADERS,
        json={"priority": new_priority}
    )
    requests.post(
        f"https://api.clickup.com/api/v2/task/{task_id}/tag/eased",
        headers=HEADERS
    )
    requests.post(
        f"https://api.clickup.com/api/v2/task/{task_id}/comment",
        headers=HEADERS,
        json={"comment_text": f"Auto-eased after {days_stale(task)} days inactive."}
    )

def run():
    for task in get_tasks():
        if days_stale(task) >= 3 and not already_eased(task):
            apply_ease(task)
            print(f"Eased: {task['name']}")

if __name__ == "__main__":
    run()

