"""最小的 HTTP 包裝：回傳 (bytes|None, 狀態字串)，狀態格式給 fulltext 判斷要不要重試。"""
import json
import os
import socket
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
        return None, f"conn_error({getattr(e, 'reason', e)})"


def get_json(url, **kw):
    data, status = get(url, accept="application/json", **kw)
    if data is None:
        raise RuntimeError(f"{status} {url}")
    return json.loads(data)


def openalex_params():
    key = os.environ.get("OPENALEX_API_KEY")
    return f"&api_key={key}" if key else ""
