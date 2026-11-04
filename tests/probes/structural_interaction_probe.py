"""Test-only prompt/selection observer. No input values, root values or credentials recorded."""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

from visidata import vd

probe, launcher, directory, *arguments = sys.argv[1:]
name = arguments[arguments.index('--store-id') + 1]
log = Path(directory) / (name + '-interaction.jsonl')
log.parent.mkdir(parents=True, exist_ok=True)


def event(kind, prompt):
    sheet = vd.activeSheet
    local = getattr(sheet, 'local', None)
    row = getattr(sheet, 'cursorRow', None)
    record = {'event': kind, 'prompt': prompt, 'local_path': local.path if local else None,
              'row_index': getattr(sheet, 'cursorRowIndex', None),
              'selected': row.get('key') if row else None, 'confirm': vd.options.confirm}
    with log.open('a') as out: out.write(json.dumps(record) + '\n')


original = vd.input


def observed(prompt, *args, **kwargs):
    event('before', prompt)
    try:
        result = original(prompt, *args, **kwargs)
    except BaseException:
        event('cancelled', prompt)
        raise
    event('after-' + (result if result in {'n','d','q','r'} else 'other') if prompt == ':' else 'after', prompt)
    return result


original_confirm = vd.confirm


def observed_confirm(prompt, *args, **kwargs):
    event('confirm-before', prompt)
    try:
        return original_confirm(prompt, *args, **kwargs)
    finally:
        event('confirm-after', prompt)


vd.confirm = observed_confirm
vd.input = observed
sys.argv = [probe, launcher, directory, *arguments]
runpy.run_path(probe, run_name='__main__')
