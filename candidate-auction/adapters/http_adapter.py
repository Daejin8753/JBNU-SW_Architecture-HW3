"""HTTP 요청 ↔ 코어 계약 변환(클라이언트 쪽 어댑터), SSE.

업무 규칙을 두지 않는다. 요청을 코어 호출로 바꾸고 결과를 응답으로 바꾸기만 한다.
"""
import json
import os
import queue
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from kernel import contract
from kernel.flow import Reply
from kernel.kernel import STATUS, CallError, Events
from kernel.trace import hop

MAX_BODY = 1024 * 1024
HEARTBEAT_SEC = 15
ID = r"([a-z0-9_]{1,40})"
STATIC = {"index.html": "text/html; charset=utf-8",
          "app.js": "text/javascript; charset=utf-8",
          "style.css": "text/css; charset=utf-8"}

# (메서드, 경로 정규식, 처리 이름, 추적 여부)
ROUTES = [
    ("GET", r"/api/plugins", "plugins", True),
    ("POST", r"/api/plugins/rescan", "rescan", True),
    ("POST", rf"/api/plugins/{ID}/install", "install", True),
    ("POST", rf"/api/plugins/{ID}/remove", "remove", True),
    ("GET", r"/api/trace", "trace_list", False),
    ("GET", rf"/api/trace/{ID}", "trace_get", False),
    ("GET", r"/api/auctions", "auctions", True),
    ("POST", r"/api/auctions", "create", True),
    ("GET", rf"/api/auctions/{ID}", "auction", True),
    ("POST", rf"/api/auctions/{ID}/bids", "bid", True),
    ("GET", r"/api/notifications", "notifications", True),
    ("GET", r"/api/events", "events", False),
]
ROUTES = [(m, re.compile(f"^{p}$"), n, t) for m, p, n, t in ROUTES]


class HttpError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class Handler(BaseHTTPRequestHandler):
    server_version = "AuctionKernel/1.0"

    def log_message(self, fmt, *args):
        pass  # 콘솔을 조용히 둔다

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    # ---- 응답 ----
    def _send(self, status, body, trace_id=None):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if trace_id:
            self.send_header("X-Trace-Id", trace_id)
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status, code, message, trace_id=None):
        body = {"ok": False, "error": {"code": code, "message": message}}
        if trace_id:
            body["trace_id"] = trace_id
        self._send(status, body, trace_id)

    def _static(self, name):
        path = os.path.join(self.server.ui_dir, name)
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", STATIC[name])
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ---- 요청 검사 ----
    def _check_origin(self):
        port = self.server.server_address[1]
        host = self.headers.get("Host", "")
        if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            raise HttpError(403, "forbidden", "허용되지 않은 Host")
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{host}":
            raise HttpError(403, "forbidden", "출처가 다른 요청")

    def _read_body(self):
        length = self.headers.get("Content-Length")
        if length is None:
            self.close_connection = True
            raise HttpError(411, "length_required", "Content-Length 필요")
        try:
            n = int(length)
        except ValueError:
            self.close_connection = True
            raise HttpError(400, "bad_request", "Content-Length 가 잘못됨")
        if n > self.server.max_body:
            self.close_connection = True
            raise HttpError(413, "too_large", "요청 본문이 너무 큼")
        raw = self.rfile.read(n) if n > 0 else b""
        if not raw.strip():
            return {}
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise HttpError(400, "bad_request", "JSON 이 아님")
        if not isinstance(body, dict):
            raise HttpError(400, "bad_request", "JSON 객체가 필요")
        return body

    # ---- 분배 ----
    def _dispatch(self, method):
        url = urlsplit(self.path)
        path, query = url.path, parse_qs(url.query)
        try:
            if method == "GET" and path == "/":
                return self._static("index.html")
            if method == "GET" and path.startswith("/ui/"):
                name = path[4:]
                if name not in STATIC:
                    raise HttpError(404, "not_found", "없는 파일")
                return self._static(name)
            route = None
            for m, rx, name, traced in ROUTES:
                mt = rx.match(path)
                if mt and m == method:
                    route = (name, mt.groups(), traced)
                    break
            if route is None:
                raise HttpError(404, "not_found", "없는 경로")
            body = {}
            if method == "POST":
                self._check_origin()
                body = self._read_body()
        except HttpError as e:
            return self._error(e.status, e.code, e.message)

        name, args, traced = route
        if name == "events":
            return self._sse()
        if not traced:
            try:
                return self._send(200, dict(getattr(self, "h_" + name)(args, query, body), ok=True))
            except HttpError as e:
                return self._error(e.status, e.code, e.message)

        tracer = self.server.tracer
        with tracer.request(f"{method} {path}") as tr:
            after = None
            try:
                with hop("http_adapter", "kernel", f"{method} {path}"):
                    result = getattr(self, "h_" + name)(args, query, body)
                if isinstance(result, Reply):
                    result, after = result.body, result.after
                status, out = 200, dict(result, ok=True, trace_id=tr.id)
            except HttpError as e:
                status, out = e.status, {"ok": False, "trace_id": tr.id,
                                         "error": {"code": e.code, "message": e.message}}
            except CallError as e:
                status, out = STATUS.get(e.code, 500), {
                    "ok": False, "trace_id": tr.id,
                    "error": {"code": e.code, "message": e.message}}
            except Exception as e:
                status, out = 500, {"ok": False, "trace_id": tr.id,
                                    "error": {"code": "internal", "message": type(e).__name__}}
        self._send(status, out, tr.id)
        if after is not None:
            after()  # 응답을 보낸 뒤 SSE 이벤트

    # ---- 처리: 코어 호출로 바꾸기만 한다 ----
    def h_plugins(self, args, query, body):
        k = self.server.kernel
        return {"plugins": k.list_plugins(), "contract_version": contract.CONTRACT_VERSION,
                "extension_points": {kind: contract.describe(spec)
                                     for kind, spec in contract.EXTENSION_POINTS.items()}}

    def h_rescan(self, args, query, body):
        return {"plugins": self.server.kernel.rescan()}

    def h_install(self, args, query, body):
        return {"plugin": self.server.kernel.install(args[0])}

    def h_remove(self, args, query, body):
        return {"plugin": self.server.kernel.remove(args[0])}

    def h_trace_list(self, args, query, body):
        try:
            limit = int(query.get("limit", ["50"])[0])
        except ValueError:
            raise HttpError(400, "bad_request", "limit 은 정수")
        return {"traces": self.server.tracer.recent(max(1, min(limit, 200)))}

    def h_trace_get(self, args, query, body):
        tr = self.server.tracer.get(args[0])
        if tr is None:
            raise HttpError(404, "not_found", "trace 없음")
        return {"trace": tr}

    def h_auctions(self, args, query, body):
        return self.server.flow.list_auctions()

    def h_create(self, args, query, body):
        return self.server.flow.create_auction(body)

    def h_auction(self, args, query, body):
        return self.server.flow.get_auction(args[0])

    def h_bid(self, args, query, body):
        return self.server.flow.place_bid(args[0], body)

    def h_notifications(self, args, query, body):
        return self.server.flow.notifications(query.get("user", [""])[0])

    # ---- SSE ----
    def _sse(self):
        events = self.server.kernel.events
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        q = events.subscribe()
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    item = q.get(timeout=self.server.heartbeat)
                except queue.Empty:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    continue
                if item is Events.CLOSE:
                    break
                etype, data = item
                msg = f"event: {etype}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()
        except OSError:
            pass  # 연결이 끊김
        finally:
            events.unsubscribe(q)
            self.close_connection = True


class AuctionServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, kernel, flow, tracer, ui_dir, max_body=MAX_BODY,
                 heartbeat=HEARTBEAT_SEC):
        self.kernel, self.flow, self.tracer = kernel, flow, tracer
        self.ui_dir, self.max_body, self.heartbeat = ui_dir, max_body, heartbeat
        super().__init__(("127.0.0.1", port), Handler)

    def stop(self):
        """구독 큐에 종료 표시를 넣어 깨우고, 서버를 내린다."""
        self.kernel.events.close_all()
        self.shutdown()
        self.server_close()
