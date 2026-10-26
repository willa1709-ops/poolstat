import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
config = json.loads((root / 'config/pools.json').read_text())
data = json.loads((root / 'data/pools.json').read_text())['pools']
fields = ('source_url', 'updates_url', 'updates_label', 'lane_source_url', 'lane_source_label')
by_id = {pool['id']: pool for pool in config}
assert set(by_id) == {pool['id'] for pool in data}
for pool in data:
    source = by_id[pool['id']]
    for field in fields:
        assert pool.get(field) == source.get(field), (pool['id'], field)
print('Published links match configuration')
