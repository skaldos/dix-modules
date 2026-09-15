#!/usr/bin/env python3
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2] / "sway"
sys.path.insert(0, str(MODULE_ROOT))
from management_entry import main

raise SystemExit(main(module_root=MODULE_ROOT))
