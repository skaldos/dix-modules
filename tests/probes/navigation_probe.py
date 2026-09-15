from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
direction = sys.argv[2]
target = None if len(sys.argv) == 3 else sys.argv[3]
sys.path.insert(0, str(root))
import navigation_entry

out = io.StringIO()
err = io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    code = navigation_entry.main(
        [direction] + ([] if target is None else ["--target", target]), root
    )
print(
    json.dumps(
        {
            "code": code,
            "stdout": out.getvalue(),
            "stderr": err.getvalue(),
            "commands": getattr(sys.modules.get("i3ipc"), "commands", []),
            "loaded": sorted(
                name
                for name in (
                    "roba",
                    "httpx",
                    "pydantic",
                    "typer",
                    "click",
                    "skaldos_sway_group_navigation",
                    "skaldos_sway_active_members",
                )
                if name in sys.modules
            ),
        },
        sort_keys=True,
    )
)
