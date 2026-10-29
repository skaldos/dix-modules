from __future__ import annotations

import json


def test_privileged_status_reads_its_record_and_never_echoes_failure_values(load_runtime, api, capsys, monkeypatch):
    Runtime = load_runtime('cockpit/apps/store_status/runtime.py')
    secret = 'synthetic-owner-visible'
    value = {'definition': {'store_id': 'one', 'provider': 'roba',
             'connection': {'context_locator': 'unix:/tmp/one.sock', 'token': secret}},
             'revision': '0'*32}
    reads, logos = [], []
    runtime = Runtime(context=None, config={}, catalog=api(
        record=lambda ident, session: reads.append((ident, session)) or value))
    monkeypatch.setattr(runtime, '_logo', lambda logo: logos.append(logo))
    argv = ['--session', 'a', '--store-id', 'one', '--logo', 'roba', '--once']
    assert runtime.main(argv) == 0
    text = capsys.readouterr().out
    assert json.loads(text.split('\n', 1)[1]) == value
    assert secret in text and secret not in ' '.join(argv)
    assert reads == [('one', 'a')] and logos == ['roba']
    runtime.catalog = api(record=lambda *_: (_ for _ in ()).throw(RuntimeError(secret)))
    assert runtime.main(argv) == 2
    error = capsys.readouterr().err
    assert secret not in error and 'RuntimeError' in error
