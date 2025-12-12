import json, os, re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

WATCH_URL = os.getenv("WATCH_URL", "http://www.e-maple.net/classified.html?area=MO&cat=WO")
OPEN_URL  = os.getenv("OPEN_URL",  WATCH_URL)

STATE_PATH = Path("state.json")
LINE_TOKEN = os.getenv("LINE_TOKEN", "").strip()

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; emaple-watcher/1.0)"}
DT_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\b")

def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"seen": {}}
    try:
        d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": {}}
    if "seen" not in d or not isinstance(d["seen"], dict):
        d = {"seen": {}}
    return d

def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

def fetch_seen(limit: int = 80) -> dict:
    r = requests.get(WATCH_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    seen = {}
    for a in soup.select("a[href*='classified/item.html?no=']"):
        href = a.get("href", "")
        m = re.search(r"no=(\d+)", href)
        if not m:
            continue
        no = m.group(1)

        ctx = a.parent.get_text(" ", strip=True) if a.parent else a.get_text(" ", strip=True)
        dtm = DT_RE.search(ctx)
        dt = dtm.group(1) if dtm else ""

        if no not in seen or (not seen[no] and dt):
            seen[no] = dt

        if len(seen) >= limit:
            break

    return seen

def line_send(text: str) -> None:
    if not LINE_TOKEN:
        raise RuntimeError("LINE_TOKEN is not set (GitHub Secretsに登録してください)")

    url = "https://api.line.me/v2/bot/message/broadcast"
    payload = {"messages": [{"type": "text", "text": text}]}
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"},
        json=payload,
        timeout=20,
    )
    r.raise_for_status()

def main():
    state = load_state()
    prev = state["seen"]
    curr = fetch_seen()

    if not prev:
        save_state({"seen": curr})
        print("init: saved baseline")
        return

    new_items = [no for no in curr if no not in prev]
    updated_items = [no for no, dt in curr.items() if (no in prev and dt and prev.get(no, "") != dt)]

    if new_items or updated_items:
        def fmt(lst):
            return ", ".join(lst[:5]) + (f" …(+{len(lst)-5})" if len(lst) > 5 else "")

        parts = []
        if new_items:
            parts.append(f"新規 {len(new_items)}件(ID:{fmt(new_items)})")
        if updated_items:
            parts.append(f"更新 {len(updated_items)}件(ID:{fmt(updated_items)})")

        msg = " / ".join(parts) + f"\n{OPEN_URL}"
        line_send(f"e-Maple（モントリオール）\n{msg}")

        save_state({"seen": curr})
        print("notified and saved state")
    else:
        print("no changes")

if __name__ == "__main__":
    main()
