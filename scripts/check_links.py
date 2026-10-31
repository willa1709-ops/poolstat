"""Validate configuration and optionally the freshly generated publication payload."""
import argparse
import ipaddress
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

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


def validate_refresh(config, payload):
    """Reject a partial refresh before it can replace the last valid snapshot."""
    validate_payload(config, payload)
    if payload.get('timezone') != 'Europe/Prague':
        raise ValueError('Expected Europe/Prague timezone')
    generated = datetime.fromisoformat(payload['generated_at'])
    if generated.tzinfo is None:
        raise ValueError('generated_at must include a timezone')
    age = datetime.now(generated.tzinfo) - generated
    if not -timedelta(minutes=5) <= age <= timedelta(hours=1):
        raise ValueError('Generated snapshot is not fresh')
    today = generated.astimezone(ZoneInfo('Europe/Prague')).date().isoformat()
    expected = {p['id']: p for p in config}
    for pool in payload['pools']:
        original = expected[pool['id']]
        if pool.get('weekly_hours') != original.get('weekly_hours'):
            raise ValueError(f"{pool['id']}: weekly schedule differs from configuration")
        if pool.get('fetched_at') != payload['generated_at'] or pool.get('date') != today:
            raise ValueError(f"{pool['id']}: inconsistent refresh timestamp")
        if original.get('status') == 'reconstruction':
            continue
        if pool.get('source_fetch_ok') is not True:
            raise ValueError(f"{pool['id']}: official source could not be fetched")
        # Výšinka has a public programme calendar, not a per-lane data feed.
        if not original.get('lane_feed_url'):
            continue
        lanes = pool.get('lane_availability')
        if not isinstance(lanes, dict) or not lanes.get('days', {}).get(today):
            raise ValueError(f"{pool['id']}: today's configured lane feed is unavailable")
        if lanes.get('fetched_at') != payload['generated_at'] or lanes.get('source_url') != original['lane_feed_url']:
            raise ValueError(f"{pool['id']}: lane feed provenance differs from configuration")
        for day, slots in lanes['days'].items():
            datetime.strptime(day, '%Y-%m-%d')
            previous_end = 0
            for slot in slots:
                def minutes(value):
                    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d|24:00', value):
                        raise ValueError(f"Invalid lane time: {value!r}")
                    hours, minute = map(int, value.split(':'))
                    return hours * 60 + minute
                start, end = minutes(slot['from']), minutes(slot['to'])
                if not previous_end <= start < end <= 1440:
                    raise ValueError(f"{pool['id']}: invalid or overlapping lane intervals")
                if slot['known_lanes'] != original['total_lanes'] or type(slot['free']) is not int or not 0 <= slot['free'] <= original['total_lanes']:
                    raise ValueError(f"{pool['id']}: invalid lane count")
                previous_end = end


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path)
    parser.add_argument('--require-live', action='store_true', help='Require a complete, fresh snapshot from every configured source')
    args = parser.parse_args()
    config = json.loads((ROOT / 'config/pools.json').read_text(encoding='utf-8'))
    validate_config(config)
    if args.data:
        validate = validate_refresh if args.require_live else validate_payload
        validate(config, json.loads(args.data.read_text(encoding='utf-8')))
    elif args.require_live:
        parser.error('--require-live needs --data')
    print(f'Configured links valid for {len(config)} pools')


if __name__ == '__main__':
    main()
