"""HTTP 요청 ↔ 코어 계약 변환(클라이언트 쪽 어댑터). 업무 규칙을 두지 않는다."""
import json
import os
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kernel import flow
from kernel.kernel import CallError
from kernel.trace import Trace

NAME_RE = re.compile(r"^[a-z0-9_]{1,40}$")
TRACE_RE = re.compile(r"^[0-9a-f]{8}$")
FILE_RE = re.compile(r"^/api/files/([0-9a-f]{12})\.md$")
PLUGIN_RE = re.compile(r"^/api/plugins/([^/]+)/(install|remove)$")
UI_FILES = {"index.html": "text/html; charset=utf-8",
            "app.js": "text/javascript; charset=utf-8",
            "style.css": "text/css; charset=utf-8"}
MAX_BODY = 1024 * 1024
MAX_UPLOAD = 20 * 1024 * 1024


class Server(ThreadingHTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    kernel = None
    ui_dir = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    # 응답 ----------------------------------------------------------------
    def _send(self, status, body, ctype, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj, trace_id=None):
        if trace_id:
            obj["trace_id"] = trace_id
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8",
                   {"X-Trace-Id": trace_id} if trace_id else None)

    def _err(self, status, code, message, trace_id=None):
        self._json(status, {"ok": False, "error": {"code": code, "message": message}}, trace_id)

    def _call(self, label, op, fn):
        """trace 를 만들고 코어를 부른다. (trace, 상태, 결과 또는 오류 본문)."""
        trace = Trace(label)
        try:
            with trace.hop("http_adapter", "kernel", op):
                result = fn(trace)
            status, obj = 200, result
        except CallError as e:
            status, obj = e.status, {"ok": False, "error": {"code": e.code, "message": e.message}}
        except Exception as e:  # 예상하지 못한 예외도 응답으로 바꾼다
            status, obj = 500, {"ok": False, "error": {"code": "internal", "message": f"{type(e).__name__}: {e}"}}
        trace.finish(status == 200)
        self.kernel.traces.add(trace)
        return trace, status, obj

    def _traced(self, label, op, fn):
        """코어를 부른 뒤 결과를 JSON 응답으로 바꾼다."""
        trace, status, obj = self._call(label, op, fn)
        if status == 200:
            obj = {"ok": True, **obj}
        self._json(status, obj, trace.trace_id)

    def _early(self, label, status, code, message):
        """코어에 닿기 전에 거부한 요청도 hop 하나로 기록하고 trace_id 를 붙인다."""
        trace = Trace(label)
        trace.note("client", "http_adapter", code, False)
        trace.finish(False)
        self.kernel.traces.add(trace)
        self._err(status, code, message, trace.trace_id)

    # GET -----------------------------------------------------------------
    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        path = url.path
        if path == "/" or (path.startswith("/ui/") and path[4:] in UI_FILES):
            name = "index.html" if path == "/" else path[4:]
            with open(os.path.join(self.ui_dir, name), "rb") as f:
                return self._send(200, f.read(), UI_FILES[name])
        if path == "/api/trace":  # 조회 API 는 기록하지 않는다
            qs = urllib.parse.parse_qs(url.query)
            try:
                limit = max(1, min(200, int(qs.get("limit", ["50"])[0])))
            except ValueError:
                return self._err(400, "rejected", "limit 은 정수")
            return self._json(200, {"ok": True, "traces": self.kernel.traces.recent(limit)})
        if path.startswith("/api/trace/"):
            tid = path[len("/api/trace/"):]
            if not TRACE_RE.match(tid):
                return self._err(404, "not_found", "trace_id 형식이 아님")
            t = self.kernel.traces.get(tid)
            if t is None:
                return self._err(404, "not_found", "trace 없음(최근 200건만 보관)")
            return self._json(200, {"ok": True, "trace": t})
        label = f"GET {path[:80]}"
        if path == "/api/plugins":
            return self._traced(label, "list", lambda t: {"plugins": self.kernel.list_plugins(t)})
        if path == "/api/history":
            return self._traced(label, "history", lambda t: flow.history(self.kernel, t))
        if path.startswith("/api/files/"):
            m = FILE_RE.match(path)
            if not m:
                return self._early(label, 404, "not_found", "파일 없음")
            trace, status, got = self._call(label, "download", lambda t: flow.download(self.kernel, m.group(1), t))
            if status != 200:
                return self._json(status, got, trace.trace_id)
            quoted = urllib.parse.quote(got["filename"], safe="")
            return self._send(200, got["body"], "text/markdown; charset=utf-8", {
                "Content-Disposition": f"attachment; filename=\"download.md\"; filename*=UTF-8''{quoted}",
                "X-Trace-Id": trace.trace_id})
        if path.startswith("/api/"):
            return self._early(label, 404, "not_found", "없는 경로")
        return self._err(404, "not_found", "없는 경로")

    # POST ----------------------------------------------------------------
    def _origin_ok(self):
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host", "")
        if host not in hosts:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin == f"http://{host}"

    def _read_body(self, limit):
        """본문을 Content-Length 만큼 읽는다. 실패하면 (상태, 메시지)."""
        cl = self.headers.get("Content-Length")
        if cl is None:
            self.close_connection = True
            return None, (411, "Content-Length 가 필요함")
        try:
            n = int(cl)
        except ValueError:
            self.close_connection = True
            return None, (400, "Content-Length 가 정수가 아님")
        if n < 0 or n > limit:
            self.close_connection = True  # 본문을 읽지 않고 끊는다
            return None, (413, f"본문이 상한({limit // (1024 * 1024)}MB)을 넘음")
        return self.rfile.read(n), None

    EARLY_CODES = {400: "rejected", 411: "length_required", 413: "too_large"}

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        label = f"POST {path[:80]}"
        if not self._origin_ok():
            self.close_connection = True
            return self._early(label, 403, "forbidden", "출처가 다른 요청")
        body, err = self._read_body(MAX_UPLOAD if path == "/api/convert" else MAX_BODY)
        if err:
            return self._early(label, err[0], self.EARLY_CODES[err[0]], err[1])
        if path == "/api/convert":
            raw_name = urllib.parse.unquote(self.headers.get("X-Filename", ""))  # 한 번만 디코딩
            posts = [p.strip() for p in self.headers.get("X-Post", "").split(",") if p.strip()]
            return self._traced(label, "convert",
                                lambda t: flow.convert(self.kernel, body, raw_name, posts, t))
        if path == "/api/plugins/rescan":
            return self._traced(label, "rescan", lambda t: self.kernel.rescan(t))
        m = PLUGIN_RE.match(path)
        if m:
            name, action = m.groups()
            if not NAME_RE.match(name):
                return self._early(label, 404, "not_found", "플러그인 이름 형식이 아님")
            fn = self.kernel.install if action == "install" else self.kernel.remove
            return self._traced(label, action, lambda t: {"plugin": fn(name, t)})
        return self._early(label, 404, "not_found", "없는 경로")


def make_server(kernel, port, ui_dir):
    handler = type("BoundHandler", (Handler,), {"kernel": kernel, "ui_dir": ui_dir})
    return Server(("127.0.0.1", port), handler)
