import json
import os
import urllib.error
import urllib.request
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

API_V2 = "https://api.clickup.com/api/v2"
API_V3 = "https://api.clickup.com/api/v3"

# One entry per ClickUp source Jarvis should read.
# type "list"  -> task list (proven path)
# type "doc"   -> ClickUp Doc page content (unverified path — test this)
SOURCES = [
    {"name": "Weekly Goals", "type": "list", "list_name": "July list"},
    {
        "name": "What Works / Doesn't",
        "type": "doc",
        "workspace_id": "9017326142",       # Exponent workspace (v2 team id)
        "doc_id": "8cqjyhy-757",            # Guidelines doc
        "page_ids": ["8cqjyhy-1137"],       # Guidelines v.2 — What Works / Doesn't table
    },
]


def _api_get(api_key: str, base: str, path: str) -> dict:
    request = urllib.request.Request(f"{base}{path}", headers={"Authorization": api_key})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


# ---------- Task Lists (v2 — same as your working script) ----------

def find_list(api_key: str, list_name: str) -> dict:
    teams = _api_get(api_key, API_V2, "/team")["teams"]
    for team in teams:
        spaces = _api_get(api_key, API_V2, f"/team/{team['id']}/space?archived=false")["spaces"]
        for space in spaces:
            space_lists = _api_get(api_key, API_V2, f"/space/{space['id']}/list?archived=false").get("lists", [])
            for lst in space_lists:
                if lst["name"] == list_name:
                    return lst
            folders = _api_get(api_key, API_V2, f"/space/{space['id']}/folder?archived=false").get("folders", [])
            for folder in folders:
                folder_lists = _api_get(api_key, API_V2, f"/folder/{folder['id']}/list?archived=false").get("lists", [])
                for lst in folder_lists:
                    if lst["name"] == list_name:
                        return lst
    raise LookupError(f"List not found: {list_name!r}")


def get_list_tasks(api_key: str, list_id: str) -> list[dict]:
    return _api_get(api_key, API_V2, f"/list/{list_id}/task?archived=false").get("tasks", [])


def format_task(task: dict) -> str:
    status = task.get("status", {}).get("status", "?")
    assignees = ", ".join(a.get("username", "?") for a in task.get("assignees", [])) or "Unassigned"
    due = task.get("due_date")
    due_str = datetime.fromtimestamp(int(due) / 1000).strftime("%Y-%m-%d") if due else ""
    line = f"- [{status}] {task['name']} | Assignees: {assignees}"
    if due_str:
        line += f" | Due: {due_str}"
    return line


def fetch_list_source(api_key: str, source: dict) -> str:
    clickup_list = find_list(api_key, source["list_name"])
    tasks = get_list_tasks(api_key, clickup_list["id"])
    lines = [f"# {source['name']} (list: {clickup_list['name']}, {len(tasks)} tasks)"]
    lines += [format_task(t) for t in tasks]
    return "\n".join(lines)


# ---------- Docs (v3 — untested, verify before trusting) ----------

def get_doc_pages(api_key: str, workspace_id: str, doc_id: str) -> list[dict]:
    return _api_get(api_key, API_V3, f"/workspaces/{workspace_id}/docs/{doc_id}/pages")


def get_page_content(api_key: str, workspace_id: str, doc_id: str, page_id: str) -> dict:
    return _api_get(
        api_key, API_V3,
        f"/workspaces/{workspace_id}/docs/{doc_id}/pages/{page_id}?content_format=text/md"
    )


def fetch_doc_source(api_key: str, source: dict) -> str:
    pages = get_doc_pages(api_key, source["workspace_id"], source["doc_id"])
    page_ids = source.get("page_ids")
    if page_ids:
        allowed = set(page_ids)
        pages = [page for page in pages if page["id"] in allowed]
    lines = [f"# {source['name']} (doc, {len(pages)} pages)"]
    for page in pages:
        content = get_page_content(api_key, source["workspace_id"], source["doc_id"], page["id"])
        lines.append(f"## {page.get('name', page['id'])}")
        lines.append(content.get("content", "(no content field returned — check raw response shape)"))
    return "\n".join(lines)


def fetch_all(api_key: str) -> str:
    blocks = []
    for source in SOURCES:
        try:
            if source["type"] == "list":
                blocks.append(fetch_list_source(api_key, source))
            elif source["type"] == "doc":
                blocks.append(fetch_doc_source(api_key, source))
            else:
                raise ValueError(f"Unknown source type: {source['type']}")
        except urllib.error.HTTPError as exc:
            blocks.append(f"# {source['name']} — FAILED: {exc.code} {exc.reason}")
    return "\n\n".join(blocks)


def main() -> None:
    api_key = os.getenv("CLICKUP_API_KEY")
    if not api_key:
        raise SystemExit("CLICKUP_API_KEY is not set")
    print(fetch_all(api_key))

if __name__ == "__main__":
    main()