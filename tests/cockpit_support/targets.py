from __future__ import annotations

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

