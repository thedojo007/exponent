import json
import os
import urllib.error
import urllib.request
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.clickup.com/api/v2"
LIST_NAME = "July list"


def _api_get(api_key: str, path: str) -> dict:
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={"Authorization": api_key},
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def find_list(api_key: str, list_name: str) -> dict:
    """Find a ClickUp list by exact name across all teams/spaces/folders."""
    teams = _api_get(api_key, "/team")["teams"]

    for team in teams:
        spaces = _api_get(api_key, f"/team/{team['id']}/space?archived=false")["spaces"]
        for space in spaces:
            space_lists = _api_get(api_key, f"/space/{space['id']}/list?archived=false").get("lists", [])
            for lst in space_lists:
                if lst["name"] == list_name:
                    return lst

            folders = _api_get(api_key, f"/space/{space['id']}/folder?archived=false").get("folders", [])
            for folder in folders:
                folder_lists = _api_get(api_key, f"/folder/{folder['id']}/list?archived=false").get("lists", [])
                for lst in folder_lists:
                    if lst["name"] == list_name:
                        return lst

    raise LookupError(f"List not found: {list_name!r}")


def get_list_tasks(api_key: str, list_id: str) -> list[dict]:
    return _api_get(api_key, f"/list/{list_id}/task?archived=false").get("tasks", [])


def format_task(task: dict) -> str:
    status = task.get("status", {}).get("status", "?")
    assignees = ", ".join(a.get("username", "?") for a in task.get("assignees", [])) or "Unassigned"

    due = task.get("due_date")
    due_str = ""
    if due:
        due_str = datetime.fromtimestamp(int(due) / 1000).strftime("%Y-%m-%d")

    line = f"- [{status}] {task['name']} | Assignees: {assignees}"
    if due_str:
        line += f" | Due: {due_str}"
    return line


def main() -> None:
    api_key = os.getenv("CLICKUP_API_KEY")
    if not api_key:
        raise SystemExit("CLICKUP_API_KEY is not set")

    try:
        clickup_list = find_list(api_key, LIST_NAME)
        tasks = get_list_tasks(api_key, clickup_list["id"])
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"ClickUp API error: {exc.code} {exc.reason}") from exc

    print(f"List: {clickup_list['name']} (id={clickup_list['id']})\n")
    print(f"Task count: {len(tasks)}\n")
    for task in tasks:
        print(format_task(task))


if __name__ == "__main__":
    main()
