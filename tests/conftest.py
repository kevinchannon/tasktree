import os

import pytest


_TT_RUNTIME_ENV_VARS = (
    "TT_CONTAINERIZED_RUNNER",
    "TT_PROJECT_ROOT",
    "TT_CALL_CHAIN",
)


@pytest.fixture(autouse=True)
def _isolate_tt_runtime_env(monkeypatch):
    for name in _TT_RUNTIME_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield
