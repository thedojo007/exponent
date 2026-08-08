# task_easer.py
import requests, os, logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
 
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
 
API_KEY = os.getenv("CLICKUP_API_KEY")
LIST_ID = os.getenv("TASK_EASER_LIST_ID")  # Task Easer Machine list
HEADERS = {"Authorization": API_KEY}
 
TAG_NAME = "needs easing"
 
logging.basicConfig(
    filename=BASE_DIR / "task_easer.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
 
# priority ladder: lower number = higher urgency in ClickUp (1=Urgent...4=Low)
def ease_priority(current):
    return min(int(current or 3) + 1, 4)  # step down one notch, floor at Low
 
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
    return any(t["name"] == TAG_NAME for t in task.get("tags", []))
 
def post_comment(task_id, text):
    """Best-effort comment post. Failures here are only logged, never raised,
    so a broken comment call can't mask or block the real failure it's reporting."""
    try:
        r = requests.post(
            f"https://api.clickup.com/api/v2/task/{task_id}/comment",
            headers=HEADERS,
            json={"comment_text": text},
        )
        r.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Failed to post comment on task {task_id}: {e}")
 
def apply_ease(task):
    task_id = task["id"]
    task_name = task["name"]
    new_priority = ease_priority(task["priority"]["id"] if task["priority"] else None)
 
    try:
        r = requests.put(
            f"https://api.clickup.com/api/v2/task/{task_id}",
            headers=HEADERS,
            json={"priority": new_priority},
        )
        r.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Priority update failed for '{task_name}' ({task_id}): {e}")
        post_comment(task_id, f"⚠️ Auto-ease failed at priority update step: {e}")
        return  # don't tag or log success if the actual ease didn't happen
 
    try:
        r = requests.post(
            f"https://api.clickup.com/api/v2/task/{task_id}/tag/{TAG_NAME}",
            headers=HEADERS,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Tagging failed for '{task_name}' ({task_id}): {e}")
        post_comment(task_id, f"⚠️ Priority was eased but tagging '{TAG_NAME}' failed: {e}")
        # priority change already succeeded — continue to log it, but flag the partial state
        post_comment(task_id, f"Auto-eased after {days_stale(task)} days inactive. (tag failed, see above)")
        return
 
    post_comment(task_id, f"Auto-eased after {days_stale(task)} days inactive.")
    logging.info(f"Eased: {task_name} ({task_id})")
 
def run():
    try:
        tasks = get_tasks()
    except requests.RequestException as e:
        logging.error(f"Failed to fetch task list: {e}")
        return
 
    for task in tasks:
        if days_stale(task) >= 3 and not already_eased(task):
            apply_ease(task)
            print(f"Eased: {task['name']}")
 
if __name__ == "__main__":
    run()