"""最小的 HTTP 包裝：回傳 (bytes|None, 狀態字串)，狀態格式給 fulltext 判斷要不要重試。"""
import json
import os
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from urllib.parse import unquote, urlparse

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) phdeasy/0.1 (academic literature pipeline)"
LOCAL_UA = "phdeasy/0.1"


def user_agent(url):
    host = urlparse(url).hostname or ""
    return LOCAL_UA if host in ("127.0.0.1", "localhost", "::1") else UA


_last = [0.0]


def get(url, accept="*/*", headers=None, timeout=30, min_interval=0.3):
    if url.startswith("file://"):
        p = unquote(urlparse(url).path)
        if os.path.exists(p):
            with open(p, "rb") as f:
                return f.read(), "ok"
        return None, "file_missing"
    wait = min_interval - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": user_agent(url), "Accept": accept, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), "ok"
    except urllib.error.HTTPError as e:
        return None, f"http_{e.code}"
    except (socket.timeout, TimeoutError):
        return None, "timeout"
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        if isinstance(getattr(e, "reason", e), ssl.SSLCertVerificationError):
            return _curl(url, accept, headers, timeout)  # 伺服器沒送完整憑證鏈：改用系統 curl（macOS 鑰匙圈）
        return None, f"conn_error({getattr(e, 'reason', e)})"


def _curl(url, accept, headers, timeout):
    cmd = ["curl", "-sL", "-m", str(timeout), "-A", user_agent(url), "-H", f"Accept: {accept}", "-w", "\n%{http_code}"]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    try:
        r = subprocess.run(cmd + [url], capture_output=True, timeout=timeout + 5)
    except (subprocess.TimeoutExpired, OSError):
        return None, "timeout"
    body, _, code = r.stdout.rpartition(b"\n")
    if r.returncode != 0 or not code.isdigit():
        return None, f"conn_error(curl exit {r.returncode})"
    return (body, "ok") if code.startswith(b"2") else (None, f"http_{code.decode()}")


def get_json(url, retry_429=(), **kw):
    data, status = get(url, accept="application/json", **kw)
    for pause in retry_429:  # 限流（例：Semantic Scholar 共用額度）就等一下再試
        if status != "http_429":
            break
        time.sleep(pause)
        data, status = get(url, accept="application/json", **kw)
    if data is None:
        raise RuntimeError(f"{status} {url}")
    return json.loads(data)


from pathlib import Path

# 本人的金鑰檔：放在 runs/_me/（不進 git，經 Google 雲端硬碟同步到每台電腦）；環境變數優先
SECRETS = Path(__file__).resolve().parents[2] / "runs" / "_me" / "secrets.env"


def secret(name):
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in SECRETS.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip() == name and not line.lstrip().startswith("#"):
                return v.strip().strip('"').strip("'") or None
    except OSError:
        pass
    return None


def s2_headers():
    """Semantic Scholar API 金鑰（本人申請）：環境變數 S2_API_KEY，或 runs/_me/secrets.env。"""
    key = secret("S2_API_KEY")
    return {"x-api-key": key} if key else {}


def openalex_params():
    key = os.environ.get("OPENALEX_API_KEY")
    return f"&api_key={key}" if key else ""
