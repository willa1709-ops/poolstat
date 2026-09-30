from __future__ import annotations

import json
import re
from urllib.parse import urlparse
from datetime import datetime, date, time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "pools.json"
OUT = ROOT / "data" / "pools.json"
TZ = ZoneInfo("Europe/Prague")
UA = {"User-Agent": "BazenyOkoli/0.2 (+personal pool opening-hours aggregator)"}
MAX_HTML_BYTES = 2_000_000


def parse_hhmm(v: str) -> time:
    h, m = map(int, v.split(":"))
    return time(h, m)


def interval_state(intervals, now: datetime):
    today = now.date()
    current = now.timetz().replace(tzinfo=None)
    for start_s, end_s in intervals:
        start, end = parse_hhmm(start_s), parse_hhmm(end_s)
        if start <= current < end:
            return True, f"{start_s}–{end_s}"
    return False, None


def fmt_intervals(intervals):
    return ", ".join(f"{a}–{b}" for a, b in intervals) if intervals else "—"


def fetch_text(url: str) -> str | None:
    """Fetch only ordinary HTTPS pages and cap the downloaded body size.

    The URLs come from our own config, but these checks reduce the impact of an
    accidental or malicious configuration change. No credentials are sent.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            return None
        host = parsed.hostname.lower()
        if host == "localhost" or host.endswith(".local"):
            return None

        with requests.get(
            url,
            headers=UA,
            timeout=(5, 15),
            stream=True,
            allow_redirects=True,
        ) as r:
            r.raise_for_status()
            chunks = []
            size = 0
            for chunk in r.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_HTML_BYTES:
                    return None
                chunks.append(chunk)
            content = b"".join(chunks)
            encoding = r.encoding or "utf-8"
            html = content.decode(encoding, errors="replace")
        return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    except requests.RequestException:
        return None
    except Exception:
        return None


def detect_exception(pool, text: str | None, now: datetime):
    """Best-effort detection of date-specific closures/changes in official text.

    We intentionally do not guess. If a phrase for today's date is found but cannot be
    parsed reliably, we surface a warning and keep weekly hours as fallback.
    """
    if not text:
        return None
    d = now.date()
    date_patterns = [
        rf"{d.day}\s*\.\s*{d.month}\s*\.\s*{d.year}",
        rf"{d.day:02d}\s*[./-]\s*{d.month:02d}\s*[./-]\s*{str(d.year)[-2:]}",
        rf"{d.day}\s*\.\s*{d.month}\s*\."
    ]
    if not any(re.search(p, text, flags=re.I) for p in date_patterns):
        return None

    window = text.lower()
    closed_words = ["uzavřen", "uzavřeno", "zavřen", "odstávk", "mimo provoz"]
    if any(w in window for w in closed_words):
        return {"kind": "warning", "message": "Oficiální web zmiňuje pro dnešek uzavření/odstávku; ověřte detail ve zdroji."}

    # Common format: 03.10.26 15:00 – 21:30
    m = re.search(rf"{d.day:02d}[./]{d.month:02d}[./](?:{str(d.year)[-2:]}|{d.year}).{{0,120}}?(\d{{1,2}}:\d{{2}})\s*[–-]\s*(\d{{1,2}}:\d{{2}})", text, flags=re.I)
    if m:
        return {"kind": "hours", "intervals": [[m.group(1).zfill(5), m.group(2).zfill(5)]]}
    return {"kind": "warning", "message": "Oficiální web obsahuje dnešní mimořádnou informaci; automat ji nedokázal bezpečně vyložit."}


def lane_count_best_effort(pool, now: datetime):
    """Conservative lane availability.

    For MVP we only return 0 while the public pool is closed. During public hours a lane
    count is returned only if a future source-specific parser can prove it. This prevents
    presenting invented free-lane counts.
    """
    return None


def main():
    pools = json.loads(CONFIG.read_text(encoding="utf-8"))
    now = datetime.now(TZ)
    weekday = str(now.weekday())
    result = []

    for pool in pools:
        item = {k: v for k, v in pool.items() if k not in {"weekly_hours", "check_urls"}}
        item["fetched_at"] = now.isoformat(timespec="seconds")
        item["date"] = now.date().isoformat()

        if pool.get("status") == "reconstruction":
            item["source_fetch_ok"] = None
            item.update({
                "open_now": False,
                "public_hours_today": "uzavřeno – rekonstrukce",
                "current_public_block": None,
                "free_lanes_now": 0,
                "lane_data_status": "closed",
                "warning": None,
            })
            result.append(item)
            continue

        intervals = pool.get("weekly_hours", {}).get(weekday, [])
        check_urls = pool.get("check_urls") or [pool["source_url"]]
        fetched_texts = [fetch_text(url) for url in check_urls]
        valid_texts = [text for text in fetched_texts if text]
        text = " ".join(valid_texts) if valid_texts else None
        item["source_fetch_ok"] = bool(valid_texts)
        exc = detect_exception(pool, text, now)
        warning = None
        if exc and exc["kind"] == "hours":
            intervals = exc["intervals"]
        elif exc and exc["kind"] == "warning":
            warning = exc["message"]

        open_now, block = interval_state(intervals, now)
        free = lane_count_best_effort(pool, now) if open_now else 0
        item.update({
            "open_now": open_now,
            "public_hours_today": fmt_intervals(intervals),
            "current_public_block": block,
            "free_lanes_now": free,
            "lane_data_status": "unknown" if open_now and free is None else ("closed" if not open_now else "live"),
            "warning": warning,
        })
        result.append(item)

    payload = {
        "generated_at": now.isoformat(timespec="seconds"),
        "timezone": "Europe/Prague",
        "pools": result,
        "notice": "Počet volných drah se zobrazuje jen tehdy, když jej lze spolehlivě doložit ze zdroje. Neznámá hodnota se neodhaduje."
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")

if __name__ == "__main__":
    main()
