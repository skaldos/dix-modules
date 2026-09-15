#!/usr/bin/env python3
from pathlib import Path
import sys
MODULE_ROOT=Path(__file__).resolve().parents[2]/'sway'
sys.path.insert(0,str(MODULE_ROOT))
from navigation_entry import main
raise SystemExit(main(module_root=MODULE_ROOT))
