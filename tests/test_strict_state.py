import pytest
from dix.core.composition import CompositionRuntimeContext


def context(tmp_path):
    return CompositionRuntimeContext(
        instance_id="x",
        composition_id="x",
        module_id="x",
        module_root=tmp_path,
        composition_root=tmp_path,
        config_base_dir=tmp_path,
        owner_scope_id="x",
    )


@pytest.mark.parametrize(
    "payload", ["34", "34  32\n", "034\n", "+34\n", "0\n", "34\n32\n", "34 34\n", "34\t32\n"]
)
def test_active_members_reject_noncanonical(payload, tmp_path, load_runtime):
    path = tmp_path / "members"
    path.write_text(payload)
    r = load_runtime("sway/compositions/active_members/runtime.py")(
        context=context(tmp_path), config={"path": str(path)}
    )
    with pytest.raises((ValueError, TypeError)):
        r.get()


@pytest.mark.parametrize("payload", ["", "basic", "other\n", "basic\nextra\n"])
def test_route_rejects_noncanonical(payload, tmp_path, load_runtime):
    path = tmp_path / "route"
    path.write_text(payload)
    r = load_runtime("sway/compositions/navigation_target/runtime.py")(
        context=context(tmp_path), config={"path": str(path)}
    )
    with pytest.raises(ValueError):
        r.get()


def test_private_missing_is_empty_but_existing_invalid_fails(tmp_path, load_runtime, api):
    Runtime = load_runtime("sway/compositions/groups/runtime.py")
    base = {
        "context": context(tmp_path),
        "state": api(set=lambda x: True),
        "ipc": api(focused_con_id=lambda: 1, live_con_ids=lambda: [1]),
        "active_members": api(set=lambda x: None),
        "navigation_target": api(set=lambda x: None),
    }
    r = Runtime(config={"state_file": str(tmp_path / "state")}, **base)
    assert r.list() == {}
    (tmp_path / "state").write_text("")
    with pytest.raises(ValueError):
        r.list()
