"""Validate configured external links without comparing stale checked-in data."""
import json
from pathlib import Path
from urllib.parse import urlparse

root = Path(__file__).resolve().parent.parent
pools = json.loads((root / "config/pools.json").read_text())
seen = set()
for pool in pools:
    pool_id = pool["id"]
    assert pool_id not in seen, f"Duplicate pool ID: {pool_id}"
    seen.add(pool_id)
    for field in ("source_url", "updates_url", "lane_source_url"):
        url = pool.get(field)
        if url is not None:
            parsed = urlparse(url)
            assert parsed.scheme == "https" and parsed.netloc, (pool_id, field, url)
    for label in ("updates_label", "lane_source_label"):
        if pool.get(label) is not None:
            assert isinstance(pool[label], str) and pool[label].strip(), (pool_id, label)
print(f"Configured links valid for {len(pools)} pools")
