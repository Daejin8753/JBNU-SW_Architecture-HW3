"""시험 공통: 임시 data·plugins 폴더로 앱을 만든다."""
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from app import App  # noqa: E402

PLUGINS = os.path.join(BASE, "plugins")
FIXTURES = os.path.join(BASE, "tests", "fixtures")
EXAMPLES = os.path.join(BASE, "examples")


class Env:
    """임시 폴더 한 벌. plugins 에 고른 파일만 복사한다."""

    def __init__(self, plugins=("english", "sealed_second", "dutch", "outbid_notifier"),
                 fixtures=()):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.data = os.path.join(self.tmp.name, "data")
        self.plugins = os.path.join(self.tmp.name, "plugins")
        os.makedirs(self.plugins)
        for name in plugins:
            self.add(os.path.join(PLUGINS, name + ".py"))
        for name in fixtures:
            self.add(os.path.join(FIXTURES, name + ".py"))
        self.apps = []

    def add(self, src):
        shutil.copy(src, self.plugins)

    def app(self, **kw):
        a = App(self.data, self.plugins, 0, **kw)
        self.apps.append(a)
        return a

    def close(self):
        for a in self.apps:
            try:
                a.stop()
            except Exception:
                pass
        self.tmp.cleanup()


def http(app, method, path, body=None, headers=None, raw=None):
    """실제 HTTP 왕복. (상태, JSON, 헤더)."""
    url = f"http://127.0.0.1:{app.port}{path}"
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    if method == "POST" and data is None:
        data = b"{}"
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read()), r.headers
    except urllib.error.HTTPError as e:
        with e:
            return e.code, json.loads(e.read() or b"{}"), e.headers


def wait_until(fn, timeout=3.0, step=0.02):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if fn():
            return True
        time.sleep(step)
    return fn()


def make_auction(app, type_name="english", start_price=1000, duration_sec=60, item="물품"):
    r = app.flow.create_auction({"item": item, "start_price": start_price,
                                 "duration_sec": duration_sec, "type": type_name})
    return r.body["auction"]["id"]


def bid(app, auction_id, bidder, amount=None):
    body = {"bidder": bidder}
    if amount is not None:
        body["amount"] = amount
    return app.flow.place_bid(auction_id, body).body
