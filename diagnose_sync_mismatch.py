import sys, json, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_session_sync as jss

# Read-only: fetches the live Build Log page content and shows exactly
# what's on it, plus what session.txt's Build Log bucket normalizes to,
# so the mismatch is visible instead of guessed at. Makes no writes.

page_map = jss.load_page_map()
entry = page_map.get("Jarvis: Build Log")
if not entry:
    print("[ERROR] No page_id.json entry for 'Jarvis: Build Log'")
    sys.exit(1)

live = jss.fetch_page_content(jss.WORKSPACE_ID, entry["doc_id"], entry["page_id"], jss.API_KEY)

text = jss.SESSION_FILE.read_text(encoding="utf-8")
buckets = jss.parse_buckets(text)
local = buckets.get("Jarvis: Build Log", "")

print("=" * 70)
print("RAW live page content (repr, so whitespace/hidden chars are visible):")
print(repr(live))
print("=" * 70)
print("RAW session.txt Build Log bucket content (repr):")
print(repr(local))
print("=" * 70)
print("NORMALIZED live content:")
print(repr(jss._normalize(live)))
print("=" * 70)
print("NORMALIZED session.txt content:")
print(repr(jss._normalize(local)))
print("=" * 70)
print("Is normalized local content found in normalized live content?",
      jss._normalize(local) in jss._normalize(live))