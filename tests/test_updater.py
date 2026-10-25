import io

import pytest

from pipeline.updater import ASSET, check, download, newer


def rel(tag, size=4):
    return {"tag_name": tag, "html_url": "https://github.com/x", "body": "notes",
            "assets": [{"name": ASSET, "size": size, "browser_download_url": f"https://github.com/sleepersusu/phdeasy/releases/download/{tag}/{ASSET}"}]}


def test_newer_compares_numbers_not_text():
    assert newer("v0.10.0", "v0.9.3") and not newer("v0.6.0", "v0.6.0") and not newer("v0.5.9", "v0.6.0")
    assert not newer("garbage", "v0.6.0") and not newer("v0.7.0", "dev")


def test_check_reports_available_and_handles_network_errors():
    nored = lambda: None  # 模擬網頁轉址查不到，改走 API
    assert check("v0.6.0", fetch=lambda u: rel("v0.7.0"), redirect=nored)["available"] is True
    assert check("v0.7.0", fetch=lambda u: rel("v0.7.0"), redirect=nored)["available"] is False
    def boom(u):
        raise OSError("offline")
    assert check("v0.6.0", fetch=boom, redirect=nored)["available"] is False


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_checks_size_header_and_origin(tmp_path):
    good = {"tag": "v0.7.0", "size": 4, "url": f"https://github.com/sleepersusu/phdeasy/releases/download/v0.7.0/{ASSET}"}
    p = download(good, tmp_path, opener=lambda req, timeout: Resp(b"MZab"))
    assert p.read_bytes() == b"MZab"
    with pytest.raises(ValueError):
        download(good, tmp_path, opener=lambda req, timeout: Resp(b"<htm"))  # 不是執行檔
    with pytest.raises(ValueError):
        download({**good, "url": "https://evil.example/x.exe"}, tmp_path, opener=lambda req, timeout: Resp(b"MZab"))


def test_latest_by_redirect_needs_no_api():
    from pipeline.updater import latest_release
    def no_api(u):
        raise AssertionError("不應該用 API")
    r = latest_release(fetch=no_api, redirect=lambda: "v1.2.3")
    assert r["tag"] == "v1.2.3" and r["url"].endswith("/releases/download/v1.2.3/" + ASSET)
    assert check("v1.2.0", fetch=no_api, redirect=lambda: "v1.2.3")["available"]


def test_redirect_failure_falls_back_to_api():
    from pipeline.updater import latest_release
    def boom():
        raise OSError("offline")
    assert latest_release(fetch=lambda u: rel("v0.9.0"), redirect=boom)["tag"] == "v0.9.0"
