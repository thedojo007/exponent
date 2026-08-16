# space_inventory.py
#
# Single job: print what's actually in the Jarvis space -- folders,
# lists, task counts. Read-only. No task content pulled, no docs
# (Docs API doesn't filter by space the way folders/lists do -- that's
# a separate lookup, deliberately excluded here, not solved).
#
# This exists to answer one question before Box B gets scoped: how big
# is "sweep this space", actually? Guessing that size and designing the
# synthesis prompt around the guess is the scope-calibration failure
# mode -- this script exists to remove the guess.

import os, sys
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

API_KEY = os.getenv("CLICKUP_API_KEY")
SPACE_ID = "90176624384"


def fetch_folders(space_id: str, api_key: str) -> list[dict]:
    url = f"https://api.clickup.com/api/v2/space/{space_id}/folder"
    headers = {"Authorization": api_key}
    resp = requests.get(url, headers=headers, params={"archived": "false"}, timeout=15)
    resp.raise_for_status()
    return resp.json().get("folders", [])


def fetch_folderless_lists(space_id: str, api_key: str) -> list[dict]:
    url = f"https://api.clickup.com/api/v2/space/{space_id}/list"
    headers = {"Authorization": api_key}
    resp = requests.get(url, headers=headers, params={"archived": "false"}, timeout=15)
    resp.raise_for_status()
    return resp.json().get("lists", [])


def task_count(lst: dict) -> str:
    # ClickUp's list object includes a 'task_count' field on some
    # endpoints but not reliably all -- print what's there rather than
    # assuming it's always populated, so a missing count is visible as
    # missing, not silently reported as 0.
    return str(lst.get("task_count", "(not reported)"))


def main():
    if not API_KEY:
        print("[ERROR] Missing CLICKUP_API_KEY in .env")
        sys.exit(1)

    folders = fetch_folders(SPACE_ID, API_KEY)
    folderless = fetch_folderless_lists(SPACE_ID, API_KEY)

    total_lists = 0

    print(f"[OK] Space {SPACE_ID} inventory\n")

    for folder in folders:
        print(f"Folder: {folder.get('name')}")
        for lst in folder.get("lists", []):
            print(f"  - List: {lst.get('name'):40} tasks: {task_count(lst)}  (list_id: {lst.get('id')})")
            total_lists += 1
        print()

    if folderless:
        print("Folderless lists:")
        for lst in folderless:
            print(f"  - List: {lst.get('name'):40} tasks: {task_count(lst)}  (list_id: {lst.get('id')})")
            total_lists += 1
        print()

    print(f"[SUMMARY] {len(folders)} folders, {total_lists} lists total.")
    print("[NOTE] Docs not included in this inventory -- separate lookup, not scoped here.")


if __name__ == "__main__":
    main()