# list_context_check.py
#
# Single job: confirm task-list auth works and print each Build Log
# task's Context field + name. Nothing else. Read-only.
#
# Session-start Next Steps rendering lives in jarvis_next_steps.py.
# This script stays a probe.
import sys, os
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_next_steps import fetch_list_tasks

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

API_KEY = os.getenv("CLICKUP_API_KEY")
BUILD_LOG_LIST_ID = "901715560513"  # from list URL: /v/li/901715560513


def get_context_field(task: dict) -> str:
    """Context is a custom field (dropdown). Custom fields come back as
    a list of {name, value, type_config: {options: [...]}} dicts --
    dropdown 'value' is an index into type_config.options, not the
    label itself. Have to resolve it."""
    for cf in task.get("custom_fields", []):
        if cf.get("name") == "Context":
            value = cf.get("value")
            if value is None:
                return "(unset)"
            options = cf.get("type_config", {}).get("options", [])
            for opt in options:
                if opt.get("orderindex") == value:
                    return opt.get("name", "(unknown option)")
            return f"(unresolved index: {value})"
    return "(no Context field)"


def main():
    if not API_KEY:
        print("[ERROR] Missing CLICKUP_API_KEY in .env")
        sys.exit(1)

    tasks = fetch_list_tasks(BUILD_LOG_LIST_ID, API_KEY)
    print(f"[OK] Fetched {len(tasks)} tasks from list {BUILD_LOG_LIST_ID}\n")

    for t in tasks:
        context = get_context_field(t)
        print(f"[{context:16}] {t.get('name')}")


if __name__ == "__main__":
    main()