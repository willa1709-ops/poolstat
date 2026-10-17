from __future__ import annotations

import json
import re
from urllib.parse import urlparse
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "pools.json"
OUT = ROOT / "data" / "pools.json"
TZ = ZoneInfo("Europe/Prague")
UA = {"User-Agent": "BazenyOkoli/0.3 (+personal pool opening-hours aggregator)"}
MAX_HTML_BYTES = 2_000_000


def parse_hhmm(v: str) -> time:
    h, m = map(int, v.split(":"))
    return time(h, m)


def hhmm_minutes(v: str) -> int | None:
    try:
        h, m = map(int, v.split(":"))
        if h == 24 and m == 0:
            return 1440
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h * 60 + m
    except Exception:
        pass
    return None


def interval_state(intervals, now: datetime):
    current = now.timetz().replace(tzinfo=None)
    for start_s, end_s in intervals:
        start, end = parse_hhmm(start_s), parse_hhmm(end_s)
        if start <= current < end:
            return True, f"{start_s}–{end_s}"
    return False, None


def fmt_intervals(intervals):
    return ", ".join(f"{a}–{b}" for a, b in intervals) if intervals else "—"


def fetch_html(url: str) -> str | None:
    """Fetch a normal HTTPS page, without credentials, with a strict size cap."""
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
            timeout=(5, 20),
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
            return content.decode(encoding, errors="replace")
    except requests.RequestException:
        return None
    except Exception:
        return None


def fetch_text(url: str) -> str | None:
    html = fetch_html(url)
    if not html:
        return None
    try:
        return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    except Exception:
        return None


def detect_exception(pool, text: str | None, now: datetime):
    """Best-effort detection of today's closures/changed hours on official pages."""
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

    m = re.search(
        rf"{d.day:02d}[./]{d.month:02d}[./](?:{str(d.year)[-2:]}|{d.year}).{{0,120}}?(\d{{1,2}}:\d{{2}})\s*[–-]\s*(\d{{1,2}}:\d{{2}})",
        text,
        flags=re.I,
    )
    if m:
        return {"kind": "hours", "intervals": [[m.group(1).zfill(5), m.group(2).zfill(5)]]}
    return {"kind": "warning", "message": "Oficiální web obsahuje dnešní mimořádnou informaci; automat ji nedokázal bezpečně vyložit."}


def merge_timeline(items):
    merged = []
    for item in items:
        if (
            merged
            and merged[-1]["to"] == item["from"]
            and merged[-1]["free"] == item["free"]
            and merged[-1]["known_lanes"] == item["known_lanes"]
        ):
            merged[-1]["to"] = item["to"]
        else:
            merged.append(dict(item))
    return merged


def parse_lane_feed(url: str, total_lanes: int | None, fetched_at: str):
    """Parse explicit per-lane timed slots from the secondary lane-schedule mirror.

    A free-lane count is emitted only when every lane has an explicit slot covering
    the interval. Missing rows/slots therefore stay unknown instead of being guessed.
    """
    if not total_lanes:
        return None
    html = fetch_html(url)
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        days = {}

        for day_node in soup.select('[id^="laneDay"]'):
            day_id = day_node.get("id", "")
            m_date = re.fullmatch(r"laneDay(\d{4}-\d{2}-\d{2})", day_id)
            if not m_date:
                continue
            day = m_date.group(1)

            rows = day_node.select(".lane-row:not(.lane-row--axis)")
            if len(rows) != int(total_lanes):
                continue

            lanes = []
            for row in rows:
                slots = []
                for el in row.select(".lane-slot[title]"):
                    title = el.get("title", "")
                    m = re.match(
                        r"\s*(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})\s*·\s*([^·]+)",
                        title,
                    )
                    if not m:
                        continue
                    start_s, end_s, category = m.group(1).zfill(5), m.group(2).zfill(5), m.group(3).strip()
                    start_m, end_m = hhmm_minutes(start_s), hhmm_minutes(end_s)
                    if start_m is None or end_m is None or end_m <= start_m:
                        continue
                    kind = "public" if "veřejnost" in category.lower() else "occupied"
                    slots.append({"from": start_s, "to": end_s, "start": start_m, "end": end_m, "kind": kind})
                lanes.append(slots)

            boundaries = sorted({x for lane in lanes for slot in lane for x in (slot["start"], slot["end"])})
            timeline = []
            for start_m, end_m in zip(boundaries, boundaries[1:]):
                if end_m <= start_m:
                    continue
                mid = (start_m + end_m) / 2
                active = []
                complete = True
                for lane in lanes:
                    matches = [slot for slot in lane if slot["start"] <= mid < slot["end"]]
                    if len(matches) != 1:
                        complete = False
                        break
                    active.append(matches[0])
                if not complete:
                    continue

                timeline.append({
                    "from": f"{start_m // 60:02d}:{start_m % 60:02d}",
                    "to": "24:00" if end_m == 1440 else f"{end_m // 60:02d}:{end_m % 60:02d}",
                    "free": sum(1 for slot in active if slot["kind"] == "public"),
                    "known_lanes": len(active),
                })

            if timeline:
                days[day] = merge_timeline(timeline)

        if not days:
            return None
        return {
            "source": "jduplavat.cz",
            "source_url": url,
            "fetched_at": fetched_at,
            "days": days,
        }
    except Exception:
        return None



def parse_mb_official_lane_feed(url: str, total_lanes: int | None, fetched_at: str):
    """Parse the official Mladá Boleslav 15-minute lane occupancy grid.

    The page renders each quarter-hour cell with a stable data-nbr and stores
    occupied cells in the hidden ds_week_data JSON. Cells not listed there are free.
    """
    if not total_lanes:
        return None

    html = fetch_html(url)
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        data_el = soup.select_one(".ds_week_data")
        if not data_el:
            return None

        raw = data_el.get("value") or data_el.get_text()
        actions = json.loads(raw)
        occupied = set()
        for action in actions:
            for value in str(action.get("hours") or "").split(","):
                value = value.strip()
                if value.isdigit():
                    occupied.add(int(value))

        slots_by_day = {}
        for cell in soup.select("td.ds_td_item[data-nbr][data-draha][data-date][data-hour][data-min]"):
            try:
                nbr = int(cell.get("data-nbr"))
                lane = int(cell.get("data-draha"))
                ts = int(cell.get("data-date"))
                hour = int(cell.get("data-hour"))
                minute = int(cell.get("data-min"))
            except (TypeError, ValueError):
                continue

            if lane < 1 or lane > int(total_lanes):
                continue
            if not (0 <= hour <= 23 and minute in {0, 15, 30, 45}):
                continue

            day = datetime.fromtimestamp(ts, TZ).date().isoformat()
            key = hour * 60 + minute
            slots_by_day.setdefault(day, {}).setdefault(key, {})[lane] = nbr in occupied

        days = {}
        for day, by_minute in slots_by_day.items():
            timeline = []
            for minute in sorted(by_minute):
                lane_states = by_minute[minute]
                if len(lane_states) != int(total_lanes):
                    continue

                end = minute + 15
                timeline.append({
                    "from": f"{minute // 60:02d}:{minute % 60:02d}",
                    "to": "24:00" if end == 1440 else f"{end // 60:02d}:{end % 60:02d}",
                    "free": sum(1 for is_occupied in lane_states.values() if not is_occupied),
                    "known_lanes": len(lane_states),
                })

            if timeline:
                days[day] = merge_timeline(timeline)

        if not days:
            return None

        return {
            "source": urlparse(url).hostname or "bazenmb.cz",
            "source_url": url,
            "fetched_at": fetched_at,
            "days": days,
        }
    except Exception:
        return None


def free_lanes_at(lane_availability, now: datetime):
    if not lane_availability:
        return None
    ranges = lane_availability.get("days", {}).get(now.date().isoformat(), [])
    minute = now.hour * 60 + now.minute
    for item in ranges:
        start = hhmm_minutes(item.get("from", ""))
        end = hhmm_minutes(item.get("to", ""))
        if start is not None and end is not None and start <= minute < end:
            return item.get("free")
    return None


def main():
    pools = json.loads(CONFIG.read_text(encoding="utf-8"))
    now = datetime.now(TZ)
    fetched_at = now.isoformat(timespec="seconds")
    weekday = str(now.weekday())
    result = []

    for pool in pools:
        item = {
            k: v
            for k, v in pool.items()
            if k not in {"check_urls", "lane_feed_url", "lane_feed_kind"}
        }
        item["fetched_at"] = fetched_at
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
                "lane_availability": None,
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

        lane_availability = None
        if pool.get("lane_feed_url"):
            if pool.get("lane_feed_kind") == "mb_official_grid":
                lane_availability = parse_mb_official_lane_feed(
                    pool["lane_feed_url"],
                    pool.get("total_lanes"),
                    fetched_at,
                )
            else:
                lane_availability = parse_lane_feed(
                    pool["lane_feed_url"],
                    pool.get("total_lanes"),
                    fetched_at,
                )

        open_now, block = interval_state(intervals, now)
        free = free_lanes_at(lane_availability, now) if open_now else 0

        item.update({
            "open_now": open_now,
            "public_hours_today": fmt_intervals(intervals),
            "current_public_block": block,
            "free_lanes_now": free,
            "lane_data_status": "unknown" if open_now and free is None else ("closed" if not open_now else "live"),
            "warning": warning,
            "lane_availability": lane_availability,
        })
        result.append(item)

    payload = {
        "generated_at": fetched_at,
        "timezone": "Europe/Prague",
        "pools": result,
        "notice": "Volné dráhy se zobrazí jen tam, kde má každá dráha pro daný čas explicitní stav. Chybějící data se neodhadují."
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
