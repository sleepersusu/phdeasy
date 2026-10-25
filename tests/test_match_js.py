"""首頁比對邏輯（JS）由 node 執行測試。"""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node")
def test_match_js():
    t = Path(__file__).parent / "js" / "match.test.mjs"
    r = subprocess.run(["node", str(t)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr or r.stdout
