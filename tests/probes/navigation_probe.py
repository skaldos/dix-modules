from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
arguments = sys.argv[2:]
sys.path.insert(0, str(root))
import navigation_entry

out = io.StringIO()
err = io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    code = navigation_entry.main(arguments, root)
print(
    json.dumps(
        {
            "code": code,
            "stdout": out.getvalue(),
            "stderr": err.getvalue(),
            "commands": getattr(sys.modules.get("i3ipc"), "commands", []),
            "loaded": sorted(
                name
                for name in ("dix", "roba", "httpx", "pydantic", "typer", "click")
                if name in sys.modules
            ),
        },
        sort_keys=True,
    )
)
