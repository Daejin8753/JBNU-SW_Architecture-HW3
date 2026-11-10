"""E7 HTTP·경로, SSE, 비공개 방식의 HTTP 노출."""
import http.client as hc
import json
import queue
import threading
import time
import unittest

from helpers import Env, http


class SseClient:
    """SSE 를 읽어 (event, data) 를 큐에 넣는다. 연결이 끊기면 None."""

    def __init__(self, port):
        self.q = queue.Queue()
        self.conn = hc.HTTPConnection("127.0.0.1", port, timeout=20)
        self.conn.request("GET", "/api/events")
        self.resp = self.conn.getresponse()
        self.ready = threading.Event()
        self.t = threading.Thread(target=self._read, daemon=True)
        self.t.start()
        self.ready.wait(5)

    def _read(self):
        event = None
        try:
            while True:
                line = self.resp.fp.readline()
                if not line:
                    break
                line = line.decode("utf-8").rstrip("\n")
                if line.startswith(": connected"):
                    self.ready.set()
                elif line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    self.q.put((event, json.loads(line[6:])))
        except OSError:
            pass
        self.q.put(None)

    def next(self, etype, timeout=5):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                item = self.q.get(timeout=end - time.monotonic())
            except queue.Empty:
                break
            if item is None:
                return None
            if item[0] == etype:
                return item[1]
        raise AssertionError(f"이벤트 {etype} 를 받지 못함")

    def close(self):
        self.conn.close()


def raw_post(port, path, headers, body=b""):
    c = hc.HTTPConnection("127.0.0.1", port, timeout=5)
    c.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
    for k, v in headers.items():
        c.putheader(k, v)
    c.endheaders()
    if body:
        c.send(body)
    r = c.getresponse()
    data = json.loads(r.read() or b"{}")
    c.close()
    return r.status, data


class E7HttpTest(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.app = self.env.app().start_background()

    def tearDown(self):
        self.env.close()

    def test_api_roundtrip_and_trace(self):
        s, b, _ = http(self.app, "GET", "/api/plugins")
        self.assertEqual(s, 200)
        names = {p["name"]: p for p in b["plugins"]}
        self.assertEqual(names["english"]["state"], "active")
        self.assertEqual(names["outbid_notifier"]["runtime"], "process")
        self.assertIn("validate_bid", names["english"]["contract"])
        s, b, _ = http(self.app, "POST", "/api/auctions",
                       {"item": "책", "start_price": 100, "duration_sec": 60, "type": "english"})
        aid = b["auction"]["id"]
        http(self.app, "POST", f"/api/auctions/{aid}/bids", {"bidder": "갑", "amount": 100})
        s, b, h = http(self.app, "POST", f"/api/auctions/{aid}/bids", {"bidder": "을", "amount": 200})
        self.assertEqual(s, 200, b)
        tid = h["X-Trace-Id"]
        self.assertEqual(tid, b["trace_id"])
        s, t, _ = http(self.app, "GET", f"/api/trace/{tid}")
        self.assertEqual(s, 200)
        hops = [(x["from"], x["to"]) for x in t["trace"]["hops"]]
        # 순서: adapter → kernel → registry → plugin …
        want = [("http_adapter", "kernel"), ("kernel", "registry"), ("kernel", "plugin:english"),
                ("plugin:english", "kernel"), ("kernel", "internal:audit"),
                ("kernel", "internal:storage"), ("kernel", "plugin:outbid_notifier")]
        pos = 0
        for hp in hops:
            if pos < len(want) and hp == want[pos]:
                pos += 1
        self.assertEqual(pos, len(want), hops)
        self.assertEqual(t["trace"]["hops"][0]["parent"], None)
        self.assertTrue(all(x["parent"] is not None for x in t["trace"]["hops"][1:]))
        self.assertTrue(all(x["ok"] and x["ms"] is not None for x in t["trace"]["hops"]))
        s, lst, _ = http(self.app, "GET", "/api/trace?limit=50")
        self.assertIn(tid, [x["trace_id"] for x in lst["traces"]])
        s, b, _ = http(self.app, "GET", "/api/trace/zzzz")
        self.assertEqual(s, 404)
        s, b, _ = http(self.app, "GET", "/api/trace/BAD-ID")
        self.assertEqual(s, 404)

    def test_lifecycle_endpoints(self):
        s, b, _ = http(self.app, "POST", "/api/plugins/rescan")
        self.assertEqual(s, 200)
        s, b, _ = http(self.app, "POST", "/api/plugins/sealed_second/remove")
        self.assertEqual((s, b["plugin"]["state"]), (200, "available"))
        s, b, _ = http(self.app, "POST", "/api/plugins/sealed_second/install")
        self.assertEqual((s, b["plugin"]["state"]), (200, "active"))
        s, b, _ = http(self.app, "POST", "/api/plugins/nope/install")
        self.assertEqual(s, 404)

    def test_post_guards(self):
        port = self.app.port
        s, b, _ = http(self.app, "POST", "/api/plugins/rescan", headers={"Origin": "http://evil.example"})
        self.assertEqual((s, b["error"]["code"]), (403, "forbidden"))
        s, b, _ = http(self.app, "POST", "/api/plugins/rescan",
                       headers={"Origin": f"http://127.0.0.1:{port}"})
        self.assertEqual(s, 200)
        s, b = raw_post(port, "/api/plugins/rescan", {"Host": f"evil:{port}", "Content-Length": "2"}, b"{}")
        self.assertEqual(s, 403)
        s, b = raw_post(port, "/api/plugins/rescan", {"Host": f"127.0.0.1:{port}"})
        self.assertEqual(s, 411)
        s, b = raw_post(port, "/api/auctions", {"Host": f"localhost:{port}",
                                                "Content-Length": str(2 * 1024 * 1024)})
        self.assertEqual(s, 413)
        s, b = raw_post(port, "/api/auctions", {"Host": f"127.0.0.1:{port}", "Content-Length": "3"}, b"[1]")
        self.assertEqual(s, 400)

    def test_sse_two_subscribers_and_shutdown(self):
        a, b = SseClient(self.app.port), SseClient(self.app.port)
        self.assertTrue(wait_subs(self.app, 2))
        s, r, _ = http(self.app, "POST", "/api/auctions",
                       {"item": "램프", "start_price": 10, "duration_sec": 60, "type": "english"})
        ea, eb = a.next("auction_created"), b.next("auction_created")
        self.assertEqual(ea["id"], r["auction"]["id"])
        self.assertEqual(ea, eb)
        t0 = time.monotonic()
        self.app.stop()
        self.assertIsNone(a.next("never", 5))  # 연결이 끊긴다
        self.assertIsNone(b.next("never", 5))
        self.assertLess(time.monotonic() - t0, 6)
        self.assertEqual(self.app.kernel.events.count(), 0)
        a.close()
        b.close()

    def test_private_types_hidden(self):
        sse = SseClient(self.app.port)
        try:
            for t in ("sealed_second",):
                s, r, _ = http(self.app, "POST", "/api/auctions",
                               {"item": "비밀물건", "start_price": 100, "duration_sec": 60, "type": t})
                aid = r["auction"]["id"]
                s, r, _ = http(self.app, "POST", f"/api/auctions/{aid}/bids",
                               {"bidder": "숨은갑", "amount": 777777})
                self.assertEqual(s, 200)
                ev = sse.next("bid_accepted")
                texts = [json.dumps(ev, ensure_ascii=False),
                         json.dumps(http(self.app, "GET", "/api/auctions")[1], ensure_ascii=False),
                         json.dumps(http(self.app, "GET", f"/api/auctions/{aid}")[1], ensure_ascii=False)]
                for txt in texts:
                    self.assertNotIn("숨은갑", txt)
                    self.assertNotIn(": 777777", txt)
                self.assertEqual(ev["bid_count"], 1)
        finally:
            sse.close()


def wait_subs(app, n):
    end = time.monotonic() + 3
    while time.monotonic() < end:
        if app.kernel.events.count() >= n:
            return True
        time.sleep(0.02)
    return False


if __name__ == "__main__":
    unittest.main()
