"""
Daily Report Pipeline (OpenAI vision -> validate -> ClickUp)
------------------------------------------------------------
Picks the newest PDF scan in a watch folder, sends its pages to an OpenAI
vision model for Korean/English handwriting parsing, validates the structured
output locally, and only then posts a summary to a ClickUp inbox task.

Posting is GATED: dry-run is the default. Nothing reaches ClickUp unless you
pass --live.

Setup (use the SAME interpreter that runs this script):
  python -m pip install --upgrade openai requests python-dotenv pymupdf watchdog
  # Windows, if `python` is ambiguous:  py -3 -m pip install --upgrade ...

Environment variables (.env -- keep it in .gitignore):
  OPENAI_API_KEY         - sk-...
  CLICKUP_API_KEY        - ClickUp personal token
  CLICKUP_INBOX_TASK_ID  - Daily Report Inbox task id
  WATCH_FOLDER           - folder where scans land (default: ~/DailyReports)
  OPENAI_MODEL           - default: gpt-4o
  MAX_PAGES              - default: 6

Usage:
  python daily_report_pipeline.py                 # dry-run: parse + local preview only
  python daily_report_pipeline.py --live          # parse + post to ClickUp
  python daily_report_pipeline.py --watch         # watch folder, dry-run
  python daily_report_pipeline.py --watch --live  # watch folder, post for real
  python daily_report_pipeline.py --file path.pdf # explicit file
"""

from __future__ import annotations

import argparse
import base64
import glob
import io
import json
import os
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# --- Config ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
CLICKUP_API_KEY = os.environ.get("CLICKUP_API_KEY")
WATCH_FOLDER = os.environ.get("WATCH_FOLDER", str(Path.home() / "DailyReports"))
CLICKUP_INBOX_TASK_ID = os.environ.get("CLICKUP_INBOX_TASK_ID", "86e30wz8j")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
MAX_PAGES = int(os.environ.get("MAX_PAGES", "6"))
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "8000"))

CLICKUP_API_BASE = "https://api.clickup.com/api/v2"
PREVIEW_DIR = Path(os.environ.get("PREVIEW_DIR", str(Path.home() / "DailyReports" / "_previews")))
CLICKUP_COMMENT_LIMIT = 20000  # conservative; ClickUp rejects very long comments

VALID_PRIORITIES = {"urgent", "high", "normal", "low"}
VALID_CATEGORIES = {"outstanding", "reminder"}
REMINDER_HINTS = ("keep in mind", "remember", "standing", "참고", "기억", "유의", "상시", "note")

PARSE_PROMPT = """You are parsing a handwritten daily report PDF. The report is written in a mix of Korean and English.

Extract every task item. Return ONLY a JSON object of this exact shape:
{"tasks": [{"task": str, "completed": bool, "due_date": str|null, "priority": str,
            "category": str, "section": str|null}]}

Field rules:
- "task": the description exactly as written (preserve Korean/English mix, do NOT translate)
- "completed": true if marked with a checkmark (V, ✓, or similar), else false
- "due_date": ISO date "YYYY-MM-DD" if a date is written next to it, else null
- "priority": one of "urgent", "high", "normal", "low" ("normal" if not indicated)
- "category": "outstanding" if under a to-do/not-completed section, "reminder" if under a
  "keep in mind"/standing section
- "section": the verbatim section heading this item sits under, or null if there is none
- If handwriting is ambiguous, give your best reading and append [?] to that word.
- Include ALL items, even trivial ones. No markdown fencing, no commentary.
"""

# --- Lazy OpenAI client (so a missing key gives a readable message, not an import-time crash) ---
_client = None

def get_client():
    global _client
    if _client is None:
        try:
            from openai import OpenAI
        except ModuleNotFoundError:
            print("X The `openai` package is not installed for THIS interpreter:")
            print(f"   {sys.executable}")
            print("   Fix:  " + sys.executable + " -m pip install --upgrade openai")
            sys.exit(1)
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client

# --- PDF discovery ---
def get_latest_pdf(folder: str):
    p = Path(folder)
    if not p.is_dir():
        print(f"X WATCH_FOLDER does not exist: {folder}")
        sys.exit(1)
    pdfs = [f for f in glob.glob(os.path.join(folder, "*")) if f.lower().endswith(".pdf")]
    pdfs = [f for f in pdfs if not Path(f).name.startswith("~$")]
    if not pdfs:
        return None
    return max(pdfs, key=os.path.getmtime)

def wait_until_stable(path: str, checks: int = 3, interval: float = 1.5, timeout: float = 60.0) -> bool:
    """Scanners write incrementally. Wait until file size stops changing."""
    deadline = time.time() + timeout
    last, stable = -1, 0
    while time.time() < deadline:
        try:
            size = os.path.getsize(path)
        except OSError:
            size = -1
        stable = stable + 1 if size == last and size > 0 else 0
        if stable >= checks:
            return True
        last = size
        time.sleep(interval)
    return False

# --- PDF -> images ---
def pdf_to_images_base64(pdf_path: str) -> list[str]:
    images: list[str] = []
    try:
        import pymupdf as fitz  # PyMuPDF >= 1.24 exposes `pymupdf`; `fitz` is the legacy alias
    except ModuleNotFoundError:
        try:
            import fitz  # type: ignore
        except ModuleNotFoundError:
            fitz = None  # type: ignore

    if fitz is not None:
        with fitz.open(pdf_path) as doc:
            if doc.page_count == 0:
                raise ValueError(f"PDF has no pages: {pdf_path}")
            for i, page in enumerate(doc):
                if i >= MAX_PAGES:
                    print(f"  ! Truncating at {MAX_PAGES} pages (set MAX_PAGES to raise)")
                    break
                pix = page.get_pixmap(dpi=200)
                images.append(base64.standard_b64encode(pix.tobytes("png")).decode("utf-8"))
        return images

    try:
        from pdf2image import convert_from_path
    except ModuleNotFoundError:
        print("X Install PyMuPDF (recommended, no external deps):")
        print("   " + sys.executable + " -m pip install pymupdf")
        sys.exit(1)

    for page in convert_from_path(pdf_path, dpi=200)[:MAX_PAGES]:
        buf = io.BytesIO()
        page.save(buf, format="PNG")
        images.append(base64.standard_b64encode(buf.getvalue()).decode("utf-8"))
    return images

# --- Model call with retry + truncation/empty guards ---
def _strip_fence(raw: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.S)
    return m.group(1) if m else raw

def call_model(images: list[str], attempts: int = 4) -> str:
    content = [{"type": "text", "text": PARSE_PROMPT}]
    for b64 in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
        })

    client = get_client()
    delay = 2.0
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": content}],
                temperature=0.1,
                max_completion_tokens=MAX_OUTPUT_TOKENS,
                response_format={"type": "json_object"},
            )
        except Exception as e:  # transient: 429 / 5xx / connection
            status = getattr(e, "status_code", None)
            transient = status in (408, 409, 429, 500, 502, 503, 504) or status is None
            last_err = e
            if not transient or attempt == attempts:
                raise
            print(f"  ! {type(e).__name__} (status={status}); retry {attempt}/{attempts - 1} in {delay:.0f}s")
            time.sleep(delay)
            delay *= 2
            continue

        choice = resp.choices[0]
        finish = choice.finish_reason
        text = (choice.message.content or "").strip()

        if finish == "length":
            _dump_debug(text, "truncated")
            raise RuntimeError(
                "Model output hit the token cap (finish_reason=length). Refusing to post a "
                "partial report. Raise MAX_OUTPUT_TOKENS or lower MAX_PAGES."
            )
        if finish == "content_filter":
            raise RuntimeError("Response blocked by content filter.")
        if not text:
            _dump_debug("", f"empty_{finish}")
            raise RuntimeError(f"Model returned empty content (finish_reason={finish}).")
        return text

    raise RuntimeError(f"Model call failed after {attempts} attempts: {last_err}")

def _dump_debug(text: str, tag: str) -> Path:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    p = PREVIEW_DIR / f"debug_{tag}_{datetime.now():%Y%m%d_%H%M%S}.txt"
    p.write_text(text, encoding="utf-8")
    print(f"  ! Raw response saved: {p}")
    return p

# --- Validation ---
def validate_tasks(payload) -> list[dict]:
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = next((payload[k] for k in ("tasks", "items", "data") if k in payload), None)
    else:
        raise ValueError(f"Unexpected JSON root type: {type(payload).__name__}")
    if not isinstance(raw_items, list):
        raise ValueError("Could not find a 'tasks' array in the model response.")
    if not raw_items:
        raise ValueError("Model returned zero tasks: treat as a failed parse, not an empty report.")

    clean, problems = [], []
    for i, it in enumerate(raw_items):
        if not isinstance(it, dict):
            problems.append(f"item {i}: not an object")
            continue
        text = str(it.get("task") or "").strip()
        if not text:
            problems.append(f"item {i}: empty task text")
            continue

        completed = it.get("completed")
        if isinstance(completed, str):
            completed = completed.strip().lower() in ("true", "yes", "y", "1")
        completed = bool(completed)

        pri = str(it.get("priority") or "normal").strip().lower()
        if pri not in VALID_PRIORITIES:
            problems.append(f"item {i}: priority '{pri}' -> normal")
            pri = "normal"

        section = it.get("section")
        section = str(section).strip() if section else None

        cat = str(it.get("category") or "outstanding").strip().lower()
        if cat not in VALID_CATEGORIES:
            problems.append(f"item {i}: category '{cat}' -> outstanding")
            cat = "outstanding"
        # Fallback: heading or task text says "keep in mind" but model still said outstanding.
        if cat == "outstanding":
            haystack = f"{section or ''} {text}".lower()
            if any(h in haystack for h in REMINDER_HINTS):
                problems.append(f"item {i}: reclassified as reminder via section/text hint")
                cat = "reminder"

        due = it.get("due_date")
        if due is not None:
            due = str(due).strip()
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
                problems.append(f"item {i}: due_date '{due}' unparseable -> null")
                due = None

        clean.append({"task": text, "completed": completed, "due_date": due,
                      "priority": pri, "category": cat, "section": section})

    if problems:
        print("  ! Normalized " + str(len(problems)) + " field issue(s):")
        for p in problems[:15]:
            print(f"     - {p}")
    if not clean:
        raise ValueError("No valid task items survived validation.")
    return clean

def parse_pdf(pdf_path: str) -> list[dict]:
    print("  Converting PDF to images...")
    images = pdf_to_images_base64(pdf_path)
    print(f"  Sending {len(images)} page(s) to {OPENAI_MODEL}...")
    raw = call_model(images)
    try:
        payload = json.loads(_strip_fence(raw))
    except json.JSONDecodeError as e:
        _dump_debug(raw, "badjson")
        raise RuntimeError(f"Model output was not valid JSON: {e}") from e
    return validate_tasks(payload)

# --- Rendering / preview / posting ---
def build_comment(tasks: list[dict], pdf_name: str) -> str:
    today = date.today().isoformat()
    body = f"**Daily Report: {today} (from {pdf_name})**\n"
    body += f"_Parsed at {datetime.now():%Y-%m-%d %H:%M}_\n\n"

    outstanding = [t for t in tasks if not t["completed"] and t["category"] == "outstanding"]
    reminders   = [t for t in tasks if not t["completed"] and t["category"] == "reminder"]
    completed   = [t for t in tasks if t["completed"]]

    if outstanding:
        body += "**Outstanding (create/keep open):**\n"
        for t in outstanding:
            due = f" [due: {t['due_date']}]" if t["due_date"] else ""
            pri = f" [{t['priority']}]" if t["priority"] != "normal" else ""
            body += f"- {t['task']}{due}{pri}\n"
        body += "\n"
    if reminders:
        body += "**Standing reminders (on hold):**\n"
        for t in reminders:
            body += f"- {t['task']}\n"
        body += "\n"
    if completed:
        body += "**Completed (close matching tasks):**\n"
        for t in completed:
            body += f"- [x] {t['task']}\n"
        body += "\n"

    body += "---\n_Raw JSON for Brain processing._\n\n"
    blob = json.dumps(tasks, ensure_ascii=False, indent=2)
    candidate = body + f"```json\n{blob}\n```"
    if len(candidate) <= CLICKUP_COMMENT_LIMIT:
        return candidate
    compact = json.dumps(tasks, ensure_ascii=False, separators=(",", ":"))
    candidate = body + f"```json\n{compact}\n```"
    if len(candidate) <= CLICKUP_COMMENT_LIMIT:
        return candidate
    return body + "_JSON omitted (comment size limit); see local preview file._"

def save_preview(tasks: list[dict], pdf_name: str, comment: str) -> Path:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now():%Y%m%d_%H%M%S}_{Path(pdf_name).stem}"
    (PREVIEW_DIR / f"{stem}.json").write_text(
        json.dumps({"source_pdf": pdf_name, "parsed_at": datetime.now().isoformat(), "tasks": tasks},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    md = PREVIEW_DIR / f"{stem}.md"
    md.write_text(comment, encoding="utf-8")
    return md

def post_to_clickup(comment: str) -> dict:
    url = f"{CLICKUP_API_BASE}/task/{CLICKUP_INBOX_TASK_ID}/comment"
    headers = {"Authorization": CLICKUP_API_KEY, "Content-Type": "application/json"}
    payload = {"comment_text": comment, "notify_all": False}

    delay = 2.0
    for attempt in range(1, 4):
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code < 400:
            print(f"OK Posted to ClickUp task {CLICKUP_INBOX_TASK_ID}")
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            print(f"  ! ClickUp {resp.status_code}; retry in {delay:.0f}s")
            time.sleep(delay)
            delay *= 2
            continue
        raise RuntimeError(f"ClickUp {resp.status_code}: {resp.text[:500]}")
    raise RuntimeError("ClickUp post failed after retries.")

# --- Orchestration ---
def process_pdf(pdf_path: str, live: bool) -> None:
    print(f"Processing: {os.path.basename(pdf_path)}")
    tasks = parse_pdf(pdf_path)
    done = sum(1 for t in tasks if t["completed"])
    print(f"Extracted {len(tasks)} item(s): {done} completed, {len(tasks) - done} open")

    comment = build_comment(tasks, os.path.basename(pdf_path))
    preview = save_preview(tasks, os.path.basename(pdf_path), comment)
    print(f"Preview written: {preview}")

    if not live:
        print("DRY RUN: nothing posted. Review the preview, then rerun with --live.")
        return
    if not CLICKUP_API_KEY:
        print("X CLICKUP_API_KEY missing; cannot post.")
        sys.exit(1)
    post_to_clickup(comment)
    print("Done. Tell Brain: 'process today's report from inbox'")

def watch_mode(live: bool) -> None:
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ModuleNotFoundError:
        print("X " + sys.executable + " -m pip install watchdog")
        sys.exit(1)

    seen: set[str] = set()

    class PDFHandler(FileSystemEventHandler):
        def _handle(self, path: str):
            if not path.lower().endswith(".pdf") or path in seen:
                return
            seen.add(path)
            print(f"\nNew scan detected: {os.path.basename(path)}")
            if not wait_until_stable(path):
                print("  ! File never stopped growing; skipping.")
                return
            try:
                process_pdf(path, live)
            except Exception as e:  # never let one bad scan kill the watcher
                print(f"  X Failed on {os.path.basename(path)}: {type(e).__name__}: {e}")

        def on_created(self, event):
            if not event.is_directory:
                self._handle(event.src_path)

        def on_moved(self, event):  # many scanners write .tmp then rename
            if not event.is_directory:
                self._handle(event.dest_path)

    if not Path(WATCH_FOLDER).is_dir():
        print(f"X WATCH_FOLDER does not exist: {WATCH_FOLDER}")
        sys.exit(1)

    obs = Observer()
    obs.schedule(PDFHandler(), WATCH_FOLDER, recursive=False)
    obs.start()
    mode = "LIVE (will post)" if live else "DRY RUN (preview only)"
    print(f"Watching {WATCH_FOLDER}: {mode}. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        obs.stop()
    obs.join()

def main() -> None:
    ap = argparse.ArgumentParser(description="Daily report PDF -> ClickUp")
    ap.add_argument("--live", action="store_true", help="actually post to ClickUp (default: dry run)")
    ap.add_argument("--watch", action="store_true", help="watch WATCH_FOLDER for new PDFs")
    ap.add_argument("--file", help="explicit PDF path instead of newest in folder")
    args = ap.parse_args()

    if not OPENAI_API_KEY:
        print("X Set OPENAI_API_KEY in .env (platform.openai.com/api-keys)")
        sys.exit(1)
    if args.live and not CLICKUP_API_KEY:
        print("X --live requires CLICKUP_API_KEY in .env")
        sys.exit(1)

    if args.watch:
        watch_mode(args.live)
        return

    pdf = args.file or get_latest_pdf(WATCH_FOLDER)
    if not pdf:
        print(f"No PDFs found in {WATCH_FOLDER}")
        sys.exit(1)
    if not Path(pdf).is_file():
        print(f"X Not a file: {pdf}")
        sys.exit(1)
    process_pdf(pdf, args.live)

if __name__ == "__main__":
    main()
