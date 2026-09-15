from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DIX = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))
sys.path.insert(0, str(DIX / "src"))


@pytest.fixture
def load_runtime():
    def load(relative: str):
        path = ROOT / relative
        name = "test_" + relative.replace("/", "_").replace(".", "_")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Runtime

    return load


class Api:
    def __init__(self, **functions):
        self.functions = functions

    def require(self, name):
        return self.functions[name]


@pytest.fixture
def api():
    return Api
