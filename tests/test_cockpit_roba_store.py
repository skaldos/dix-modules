from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from roba import RobaClient


def external(store_graph):
    create, runtime, _ = store_graph
    runtime.require("start")(session="b")
    env = runtime.require("owner_environment")(session="b")
    created = RobaClient(env=env).control().context_create(context_id="data")
    owner = RobaClient(env={}).context(
        locator=f"unix:{created['socket']}", token=created["owner_token"])
    owner.set("settings", {"nested": ["first", {"message": "hello"}]})
    owner.instance_create(instance_id="one", state={"name": "example"})
    reader = owner.token_create(token_id="reader", read=["context", "instance:one"])
    sock = owner.socket_create(socket_id="reader", read=["context", "instance:one"])
    conn = {"context_id": "data", "context_locator": f"unix:{created['socket']}",
            "token": created["owner_token"], "timeout": 5.0}
    return create, runtime, owner, conn, reader, sock, env


def test_real_owner_token_socket_and_instance_navigation_is_read_only(store_graph):
    create, runtime, owner, conn, reader, sock, env = external(store_graph)
    provider = create("skaldos/cockpit/roba_store").api
    before = json.dumps(owner.snapshot(), sort_keys=True)
    control_before = RobaClient(env=env).control().contexts()
    # Canonical owner, delegated token, own socket and scoped Instance variants.
    variants = [conn, {**conn, "token": reader["token"]},
                {k: v for k, v in {**conn, "context_locator": f"unix:{sock['socket']}"}.items()
                 if k != "token"}]
    for variant in variants:
        assert provider.require("validate")(variant) == variant
        assert provider.require("root")(variant)["path"] == []
        rows = provider.require("children")(variant, [])
        assert {r["label"] for r in rows} == {"settings", "one"}
        assert provider.require("inspect")(variant, [["key", "settings"]]) == {
            "nested": ["first", {"message": "hello"}]}
        assert provider.require("children")(variant, [["key", "settings"]])[0]["label"] == "nested"
        assert provider.require("inspect")(
            variant, [["key", "settings"], ["field", "nested"], ["index", 1],
                      ["field", "message"]]) == "hello"
        assert provider.require("children")(variant, [["instance", "one"]])[0]["label"] == "name"
        scoped = {**variant, "instance_id": "one"}
        assert provider.require("inspect")(scoped, [["key", "name"]]) == "example"
    # Control grants metadata only; it never invents a Context owner token.
    paths = runtime.require("paths")(session="b")
    status = runtime.require("status")(session="b")
    control = {"daemon_id": "default", "runtime_root": env["ROBA_RUNTIME_ROOT"],
               "logs_root": env["ROBA_LOGS_ROOT"], "timeout": 5.0, "pid": status["pid"],
               "daemon_socket": paths["daemon_socket"], "control_socket": paths["control_socket"],
               "control_token": env["ROBA_CONTROL_TOKEN"]}
    assert provider.require("children")(control, [])[0]["label"] == "data"
    meta = provider.require("children")(control, [["context", "data"]])
    assert "state" not in {x["label"] for x in meta}
    after = json.dumps(owner.snapshot(), sort_keys=True)
    assert after == before
    assert RobaClient(env=env).control().contexts() == control_before
    if os.environ.get("DIX_STORE_EVIDENCE_DIR"):
        evidence = Path(os.environ["DIX_STORE_EVIDENCE_DIR"])
        evidence.mkdir(parents=True, exist_ok=True)
        # Synthetic state only: Context snapshots do not contain credential records.
        (evidence / "target-before.json").write_text(before + "\n")
        (evidence / "target-after.json").write_text(after + "\n")
        (evidence / "state-proof.json").write_text(json.dumps({
            "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
            "after_sha256": hashlib.sha256(after.encode()).hexdigest(),
            "registry_unchanged": True,
        }, indent=2) + "\n")


def test_roba_registration_and_mutation_injection_have_no_transport(store_graph, monkeypatch):
    create, _, _ = store_graph
    provider = create("skaldos/cockpit/roba_store").api
    catalog = create("skaldos/cockpit/store_catalog").api
    catalog.require("register_provider")("roba", provider)
    conn = {"context_id": "missing", "context_locator": "unix:/tmp/not-a-store.sock",
            "token": "do-not-echo-this", "timeout": 0.1}
    assert provider.require("validate")(conn) == conn
    entry = {"store_id": "offline", "provider": "roba", "connection": conn}
    catalog.require("create")(entry, "a")
    entry["store_id"] = "renamed"
    catalog.require("update")("offline", entry, "a")
    catalog.require("remove")("renamed", "a")
    # Invalid paths must be rejected even with a privileged valid connection.
    for action in ("create", "delete", "write", "token", "socket", "grant", "start", "stop"):
        for op in ("children", "inspect"):
            with pytest.raises(ValueError, match="read-only"):
                provider.require(op)(conn, [[action, "x"]])
    with pytest.raises(RuntimeError) as error:
        provider.require("children")(conn, [])
    assert "do-not-echo-this" not in str(error.value)
    assert catalog.require("list")("a") == []


def test_auth_missing_and_stale_errors_do_not_mutate_target(store_graph):
    create, runtime, owner, conn, _, _, _ = external(store_graph)
    provider = create("skaldos/cockpit/roba_store").api
    before = json.dumps(owner.snapshot(), sort_keys=True)
    with pytest.raises(RuntimeError):
        provider.require("children")({**conn, "token": "invalid-secret"}, [])
    with pytest.raises(RuntimeError):
        provider.require("inspect")(conn, [["key", "missing"]])
    with pytest.raises(RuntimeError):
        provider.require("children")(conn, [["instance", "missing"]])
    assert json.dumps(owner.snapshot(), sort_keys=True) == before
    runtime.require("stop")(session="b")
    with pytest.raises(RuntimeError):
        provider.require("children")(conn, [])


def test_positive_dispatch_and_registration_record_only_gets_on_external_target(
    store_graph, monkeypatch,
):
    from roba import TransportClient

    create, _, owner, conn, _, _, _ = external(store_graph)
    provider = create("skaldos/cockpit/roba_store").api
    catalog = create("skaldos/cockpit/store_catalog").api
    catalog.require("register_provider")("roba", provider)
    before = json.dumps(owner.snapshot(), sort_keys=True)
    original = TransportClient.request
    calls = []

    def observe(client, method, *args, **kwargs):
        if str(client.socket) == str(owner.transport.socket):
            calls.append(method)
            assert method == "GET", "external mutation reached the transport"
        return original(client, method, *args, **kwargs)

    monkeypatch.setattr(TransportClient, "request", observe)
    entry = {"store_id": "external", "provider": "roba", "connection": conn}
    catalog.require("create")(entry, "a")
    entry["store_id"] = "changed"
    catalog.require("update")("external", entry, "a")
    catalog.require("remove")("changed", "a")
    assert calls == []
    for action in ("create", "delete", "write", "grant", "token", "socket", "manage"):
        with pytest.raises(ValueError):
            provider.require("children")(conn, [[action, "x"]])
    assert calls == []
    provider.require("children")(conn, [])
    provider.require("inspect")(conn, [["key", "settings"]])
    assert calls and set(calls) == {"GET"}
    assert json.dumps(owner.snapshot(), sort_keys=True) == before


def test_instance_only_reader_never_exposes_context_values(store_graph):
    create, _, owner, conn, _, _, _ = external(store_graph)
    reader = owner.token_create(token_id="instance-only", read=["instance:one"])
    provider = create("skaldos/cockpit/roba_store").api
    value = {**conn, "token": reader["token"]}
    nodes = provider.require("children")(value, [])
    assert [n["label"] for n in nodes] == ["one"]
    assert provider.require("inspect")(value, [["instance", "one"], ["key", "name"]]) == "example"
    with pytest.raises(RuntimeError):
        provider.require("inspect")(value, [["key", "settings"]])
