"""Validate configuration and optionally the freshly generated publication payload."""
import argparse
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK_FIELDS = ('source_url', 'updates_url', 'lane_source_url')
LABEL_FIELDS = ('updates_label', 'lane_source_label')


def validate_url(value):
    if not isinstance(value, str) or not value or re.search(r'[\s\\\x00-\x1f]', value):
        raise ValueError(f'Invalid HTTPS URL: {value!r}')
    try:
        u = urlsplit(value)
        host = u.hostname
        if u.scheme != 'https' or not host or u.username is not None or u.password is not None:
            raise ValueError('HTTPS host required; credentials forbidden')
        _ = u.port
        try:
            ipaddress.ip_address(host)
        except ValueError:
            labels = host.encode('idna').decode().rstrip('.').split('.')
            if not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', x) for x in labels):
                raise ValueError('Invalid hostname')
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f'Invalid HTTPS URL: {value!r}') from exc


def validate_config(pools):
    if not isinstance(pools, list) or not pools:
        raise ValueError('Expected a nonempty pool list')
    seen = set()
    for pool in pools:
        ident = pool.get('id')
        if not isinstance(ident, str) or not ident.strip() or ident in seen:
            raise ValueError(f'Missing or duplicate pool ID: {ident!r}')
        seen.add(ident)
        validate_url(pool.get('source_url'))
        for field in (*LINK_FIELDS[1:], 'lane_feed_url'):
            if pool.get(field) is not None:
                validate_url(pool[field])
        if 'check_urls' in pool:
            if not isinstance(pool['check_urls'], list) or not pool['check_urls']:
                raise ValueError(f'{ident}: check_urls must be a nonempty list')
            for url in pool['check_urls']:
                validate_url(url)
        for label, url in zip(LABEL_FIELDS, LINK_FIELDS[1:]):
            if pool.get(label) is not None:
                if not isinstance(pool[label], str) or not pool[label].strip() or not pool.get(url):
                    raise ValueError(f'{ident}: {label} needs text and {url}')


def validate_payload(config, payload):
    pools = payload.get('pools')
    validate_config(pools)
    expected = {p['id']: p for p in config}
    if set(expected) != {p['id'] for p in pools}:
        raise ValueError('Published pool IDs differ from configuration')
    for pool in pools:
        for field in (*LINK_FIELDS, *LABEL_FIELDS):
            if pool.get(field) != expected[pool['id']].get(field):
                raise ValueError(f"{pool['id']}: published {field} differs from configuration")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path)
    args = parser.parse_args()
    config = json.loads((ROOT / 'config/pools.json').read_text(encoding='utf-8'))
    validate_config(config)
    if args.data:
        validate_payload(config, json.loads(args.data.read_text(encoding='utf-8')))
    print(f'Configured links valid for {len(config)} pools')


if __name__ == '__main__':
    main()
