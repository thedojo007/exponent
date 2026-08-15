import sys, json, os
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_session_sync as jss   # reuses fetch_page_content, write_page_content, retry, .env loading
from extract_items import extract_items, classify

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

OUTPUT_FILE = Path(__file__).resolve().parent / "next_steps.md"

# The ClickUp doc bucket this gets pushed to. Same page_id.json file
# jarvis_session_sync.py already reads -- add this key there once, the
# same way every other bucket's doc_id/page_id got added: via
# fetch_page_ids.py / list_pages.py, not by hand-parsing the doc URL.
# The URL slug (e.g. "8cqjyhy-3717") is not reliably the same as the
# API's doc_id/page_id -- guessing it risks silently overwriting the
# wrong page every run, which is worse than asking once.
NEXT_STEPS_BUCKET = "Jarvis: Next Steps"

# Types that actually answer "what should I look at next" -- everything
# else (SHIPPED, DECISION, OBSERVATION) is real history but not what
# this file is for. Deliberately narrow: this is a first-pass filter
# for a human to skim, not a complete picture of the Build Log.
NEXT_STEP_TYPES = {"NEXT_STEP", "OPEN_QUESTION"}


def build_markdown(next_steps: list[dict], total_scanned: int) -> str:
    lines = [
        "# Jarvis Next Steps (auto-extracted from Build Log)",
        "",
        "Filtered for 'Next:'/'outstanding' labels and open questions only.",
        "~50% precision expected -- skim and use judgment, this is a first",
        "pass, not a verified list. This page is fully rewritten from",
        "scratch every run, not appended to -- nothing here is permanent,",
        "don't build on top of it by hand.",
        "",
        f"_{len(next_steps)} of {total_scanned} scanned chunks kept._",
        "",
    ]

    by_date = {}
    for i in next_steps:
        by_date.setdefault(i["date"] or "(undated)", []).append(i)

    for date in sorted(by_date, key=lambda d: (d == "(undated)", d)):
        lines.append(f"## {date}")
        for i in by_date[date]:
            lines.append(f"- [{i['type']}] {i['text']}")
        lines.append("")

    return "\n".join(lines)


def main():
    page_map = jss.load_page_map()

    build_log_entry = page_map.get("Jarvis: Build Log")
    if not build_log_entry:
        print("[ERROR] No page_id.json entry for 'Jarvis: Build Log'")
        sys.exit(1)

    content = jss.fetch_page_content(jss.WORKSPACE_ID, build_log_entry["doc_id"], build_log_entry["page_id"], jss.API_KEY)

    items = extract_items(content)
    next_steps = [i for i in items if i["type"] in NEXT_STEP_TYPES]
    markdown = build_markdown(next_steps, len(items))

    # Local copy always gets written -- cheap, works offline, useful as
    # a fallback if the ClickUp push fails partway.
    OUTPUT_FILE.write_text(markdown, encoding="utf-8")
    print(f"[OK] Wrote {len(next_steps)} next-step items to {OUTPUT_FILE}")
    print(f"     ({len(items)} total chunks scanned, {len(next_steps)} kept)")

    next_steps_entry = page_map.get(NEXT_STEPS_BUCKET)
    if not next_steps_entry or not next_steps_entry.get("doc_id") or not next_steps_entry.get("page_id"):
        print(f"[SKIP] No page_id.json entry for '{NEXT_STEPS_BUCKET}' yet -- "
              f"ClickUp doc not updated. Run fetch_page_ids.py against "
              f"https://app.clickup.com/9017326142/v/dc/8cqjyhy-3717 and add "
              f"the resulting doc_id/page_id to page_id.json under "
              f'"{NEXT_STEPS_BUCKET}", same as every other bucket.')
        return

    # Full overwrite: pass only the new content, nothing concatenated
    # from what's already there. This is the one place in this whole
    # project that deliberately does NOT preserve prior content -- that
    # was requested explicitly, not a default to apply anywhere else.
    jss.write_page_content(jss.WORKSPACE_ID, next_steps_entry["doc_id"], next_steps_entry["page_id"], markdown, jss.API_KEY)
    print(f"[OK] Overwrote ClickUp doc '{NEXT_STEPS_BUCKET}' from scratch")


if __name__ == "__main__":
    main()