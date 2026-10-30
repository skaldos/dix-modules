"""Observe the real installed launcher. Record endpoint metadata, never headers or values."""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

from roba.transport import TransportClient

launcher, destination, *arguments = sys.argv[1:]
evidence = Path(destination)
evidence.mkdir(parents=True, exist_ok=True)
ident = arguments[arguments.index('--store-id') + 1]
log = evidence / (ident + '.jsonl')
original = TransportClient.request


def observed(self, method, path, **kwargs):
    selected = Path(self.socket).parent.name == 'n69'
    if selected:
        assert 'snapshot' not in path, 'Snapshot fallback is forbidden'
    try:
        result = original(self, method, path, **kwargs)
    except Exception:
        if selected:
            with log.open('a') as out:
                out.write(json.dumps({'method': method, 'path': path, 'failed': True}) + '\n')
        raise
    if selected:
        if path.endswith('state-keys'):
            assert set(result) == {'keys'}
        if path == '/context/instances':
            assert all(set(item) == {'id', 'name', 'created_at', 'updated_at'}
                       for item in result['instances'])
        with log.open('a') as out:
            out.write(json.dumps({'method': method, 'path': path, 'failed': False}) + '\n')
    return result


TransportClient.request = observed
sys.argv = [launcher, *arguments]
runpy.run_path(launcher, run_name='__main__')
