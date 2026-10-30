"""Advisory network report: never confuse a timeout with a broken link."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests

def check(url):
    try:
        with requests.get(url, timeout=(5, 15), stream=True, allow_redirects=True) as response:
            status = 'available' if response.ok else 'http_error'
            return {'url': url, 'result': status, 'http_status': response.status_code, 'final_url': response.url}
    except requests.RequestException as exc:
        return {'url': url, 'result': 'unverified', 'reason': type(exc).__name__}

if __name__ == '__main__':
    config = json.loads(Path('config/pools.json').read_text())
    urls = sorted({p[key] for p in config for key in ('source_url','updates_url','lane_source_url') if p.get(key)})
    with ThreadPoolExecutor(max_workers=4) as executor:
        report = list(executor.map(check, urls))
    Path('link-availability.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    for row in report:
        print(row)
