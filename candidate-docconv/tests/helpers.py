"""시험 공통: 임시 data·plugins 폴더와 커널·서버 준비."""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (BASE, os.path.join(BASE, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import app  # noqa: E402
from adapters.http_adapter import make_server  # noqa: E402

PLUGINS = os.path.join(BASE, "plugins")
FIXTURES = os.path.join(BASE, "tests", "fixtures")
VIOLATIONS = os.path.join(FIXTURES, "violations")
MANIFESTS = os.path.join(FIXTURES, "manifest")
EXAMPLES = os.path.join(BASE, "examples")
ALL_PLUGINS = sorted(f for f in os.listdir(PLUGINS) if f.endswith(".py"))


def make_env(tc, plugins=(), fixtures=()):
    """임시 폴더에 플러그인 파일을 복사한다. (data, plugins_dir)."""
    root = tempfile.mkdtemp(prefix="docconv_")
    tc.addCleanup(shutil.rmtree, root, True)
    pdir = os.path.join(root, "plugins")
    os.makedirs(pdir)
    for f in plugins:
        shutil.copy(os.path.join(PLUGINS, f), pdir)
    for f in fixtures:
        shutil.copy(os.path.join(FIXTURES, f), pdir)  # f 는 fixtures/ 기준 상대 경로
    return os.path.join(root, "data"), pdir


def start_kernel(tc, data, pdir):
    k = app.build_kernel(data, pdir)
    tc.addCleanup(k.shutdown)
    return k


def copy_in(src, pdir):
    shutil.copy(src, pdir)


def start_server(tc, kernel):
    srv = make_server(kernel, 0, os.path.join(BASE, "ui"))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    def stop():
        srv.shutdown()
        srv.server_close()
        t.join(5)
    tc.addCleanup(stop)
    return srv.server_address[1]


def request(port, method, path, body=None, headers=None):
    """(상태, 헤더 dict, 본문 bytes)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        h = dict(headers or {})
        if method == "POST" and body is None:
            body = b""
        conn.request(method, path, body=body, headers=h)
        r = conn.getresponse()
        return r.status, dict(r.getheaders()), r.read()
    finally:
        conn.close()


def jrequest(port, method, path, body=None, headers=None):
    status, h, raw = request(port, method, path, body, headers)
    return status, h, json.loads(raw.decode("utf-8"))


def payload(name, fmt="hangfmt", data=b"", members=None):
    """converter.convert 입력 계약에 맞는 payload."""
    return {"filename": name, "format": fmt, "data": data, "members": members or {}}


def wait_until(tc, cond, timeout=2.0, what="조건"):
    """cond() 가 참이 되기를 기다린다. timeout 안에 못 보면 시험 실패(고정 대기 아님)."""
    deadline = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > deadline:
            tc.fail(f"{timeout}초 안에 {what} 을(를) 못 봄")
        time.sleep(0.005)


class Barrier:
    """시험 쪽 장벽: 인스턴스의 handle 을 Event 가 설정될 때까지 기다린 뒤 원래 handle 을 부르는 함수로 바꾼다.

    10초 안에 설정되지 않으면 원래 handle 을 부르지 않고 실패를 기록한다. 코어 코드는 바꾸지 않는다.
    """

    def __init__(self, tc, instance, limit=10.0):
        self.event = threading.Event()
        self.failed = []
        orig = instance.handle

        def gated(op, payload, ctx):
            if not self.event.wait(limit):
                self.failed.append("장벽이 10초 안에 열리지 않음")
                raise RuntimeError("장벽 시간 초과")
            return orig(op, payload, ctx)
        instance.handle = gated
        tc.addCleanup(self.event.set)
