#!/usr/bin/env python3
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

module_root = Path(os.environ["SKALDOS_SWAY_ROOT"]).expanduser().resolve()
sys.path.insert(0, str(module_root))
main = importlib.import_module("management_entry").main
raise SystemExit(main(module_root=module_root))
