import pytest


@pytest.fixture(autouse=True)
def _clean_app_env(monkeypatch):
    """應用程式在背景跑流水線時會設 PHDEASY_HOLD=1（同步時不放開使用中）；測試不能受它影響，否則開工檢查在應用程式裡會失敗。"""
    monkeypatch.delenv("PHDEASY_HOLD", raising=False)
