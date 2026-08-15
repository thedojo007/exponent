import re

# Matches a line that's ONLY a date -- optionally bold, optionally
# colon-terminated. e.g. "**7/1**", "7/13:", "8/8:", "7/20:"
DATE_HEADER_RE = re.compile(r"^\*{0,2}(\d{1,2}/\d{1,2})\*{0,2}:?\s*$")

# Matches a line that starts with an inline date + colon but has real
# content after it on the same line -- e.g. "7/13: Shipped: X — Y".
# These showed up later in the real log as self-contained dated lines,
# not under a preceding date-header block.
INLINE_DATED_RE = re.compile(r"^(\d{1,2}/\d{1,2}):\s*(.+)$")

BULLET_RE = re.compile(r"^[\*\-\u2022]\s+(.*)$")

SHIPPED_RE = re.compile(r"\bshipped\b", re.IGNORECASE)
DECISION_RE = re.compile(r"\b(do not|never|always|confirmed)\b", re.IGNORECASE)
QUESTION_RE = re.compile(r"(\?|\bpending\b|\bunresolved\b|\bblocked\b)", re.IGNORECASE)
DEFERRED_RE = re.compile(r"\b(deferred|on hold|graveyard|superseded)\b", re.IGNORECASE)
# Not in the original spec's four categories, but this is the clearest
# "what's next" signal actually present in the real data -- explicit
# "Next:" labeled lines. Also catches "outstanding"/"open loop"/"todo"
# phrasing used elsewhere in the log for the same purpose.
NEXT_STEP_RE = re.compile(r"^(next|todo)\s*:|\boutstanding\b|\bopen loop", re.IGNORECASE)


def classify(text: str) -> str:
    if NEXT_STEP_RE.search(text):
        return "NEXT_STEP"
    if SHIPPED_RE.search(text):
        return "SHIPPED"
    if DEFERRED_RE.search(text):
        return "DEFERRED"
    if QUESTION_RE.search(text):
        return "OPEN_QUESTION"
    if DECISION_RE.search(text):
        return "DECISION"
    return "OBSERVATION"


def extract_items(content: str) -> list[dict]:
    items = []
    current_date = None
    pending_text = None  # accumulates a bullet's own continuation lines

    def flush():
        nonlocal pending_text
        if pending_text and pending_text.strip():
            text = pending_text.strip()
            items.append({
                "date": current_date,
                "text": text,
                "type": classify(text),
            })
        pending_text = None

    for raw_line in content.split("\n"):
        line = raw_line.strip()

        if not line:
            continue

        m = DATE_HEADER_RE.match(line)
        if m:
            flush()
            current_date = m.group(1)
            continue

        m = INLINE_DATED_RE.match(line)
        # Only treat as a standalone dated item if it's NOT a bullet
        # line that happens to start with a date-looking token, and
        # has enough content to be a real item (guards against
        # accidentally swallowing a bare date+colon that slipped past
        # the header regex for some formatting reason).
        if m and not BULLET_RE.match(line) and len(m.group(2)) > 3:
            flush()
            items.append({
                "date": m.group(1),
                "text": m.group(2).strip(),
                "type": classify(m.group(2)),
            })
            continue

        m = BULLET_RE.match(line)
        if m:
            flush()
            pending_text = m.group(1)
            continue

        # Non-bulleted, non-header, non-inline-dated line: either a
        # sub-bullet continuation (indented under the last bullet) or
        # a stray paragraph line under the current date. Append to
        # whatever's pending rather than starting a new item, since
        # splitting mid-thought produces garbage items.
        if pending_text is not None:
            pending_text += " " + line
        else:
            pending_text = line

    flush()
    return items


def looks_actionable(item: dict) -> bool:
    """The spec's 'skip purely observational chunks with no actionable
    noun' rule. Kept separate from classify() so the review output can
    show BOTH what got classified AND what got filtered, rather than
    silently dropping things."""
    return item["type"] != "OBSERVATION"


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from real_content import RAW

    all_items = extract_items(RAW)
    actionable = [i for i in all_items if looks_actionable(i)]
    observational = [i for i in all_items if not looks_actionable(i)]

    print(f"Total candidate chunks: {len(all_items)}")
    print(f"Classified as actionable: {len(actionable)}")
    print(f"Classified as observation (would be filtered): {len(observational)}")
    print("=" * 70)

    by_type = {}
    for i in actionable:
        by_type.setdefault(i["type"], []).append(i)

    for t, items in by_type.items():
        print(f"\n--- {t} ({len(items)}) ---")
        for i in items:
            preview = i["text"][:110] + ("..." if len(i["text"]) > 110 else "")
            print(f"  [{i['date']}] {preview}")

    print("\n" + "=" * 70)
    print("FILTERED AS OBSERVATION (for review -- is this actually right?):")
    for i in observational:
        preview = i["text"][:110] + ("..." if len(i["text"]) > 110 else "")
        print(f"  [{i['date']}] {preview}")