"""1단계: 기본 흐름(생성 → 입찰 → 마감)이 HTTP 로 된다."""
import time
import unittest

from helpers import Env, http, wait_until


class BasicFlowTest(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.app = self.env.app().start_background()

    def tearDown(self):
        self.env.close()

    def test_ui_served(self):
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{self.app.port}/", timeout=5) as r:
            self.assertIn("text/html", r.headers["Content-Type"])
        s, b, _ = http(self.app, "GET", "/ui/secret.txt")
        self.assertEqual(s, 404)

    def test_create_bid_close(self):
        s, b, h = http(self.app, "POST", "/api/auctions",
                       {"item": "자전거", "start_price": 1000, "duration_sec": 1, "type": "english"})
        self.assertEqual(s, 200, b)
        self.assertEqual(h["X-Trace-Id"], b["trace_id"])
        aid = b["auction"]["id"]
        s, b, _ = http(self.app, "POST", f"/api/auctions/{aid}/bids", {"bidder": "갑", "amount": 1000})
        self.assertEqual(s, 200, b)
        s, b, _ = http(self.app, "POST", f"/api/auctions/{aid}/bids", {"bidder": "을", "amount": 1010})
        self.assertEqual(s, 400)
        self.assertEqual(b["error"]["code"], "rejected")
        self.assertIn("1,050", b["error"]["message"])
        s, b, _ = http(self.app, "POST", f"/api/auctions/{aid}/bids", {"bidder": "을", "amount": 1050})
        self.assertEqual(s, 200, b)
        self.assertIsNone(b["notify_error"])
        # 갑이 밀려났으므로 알림이 있다
        s, b, _ = http(self.app, "GET", "/api/notifications?user=%EA%B0%91")
        self.assertEqual(len(b["notifications"]), 1)
        self.assertIn("1,050", b["notifications"][0]["message"])

        def closed():
            return http(self.app, "GET", f"/api/auctions/{aid}")[1]["auction"]["status"] == "closed"
        self.assertTrue(wait_until(closed, 3))
        a = http(self.app, "GET", f"/api/auctions/{aid}")[1]["auction"]
        self.assertEqual((a["winner"], a["price"]), ("을", 1050))
        s, b, _ = http(self.app, "POST", f"/api/auctions/{aid}/bids", {"bidder": "병", "amount": 9999})
        self.assertEqual(s, 409)

    def test_create_validation(self):
        for body in ({"item": "", "start_price": 1, "duration_sec": 1, "type": "english"},
                     {"item": "x", "start_price": 0, "duration_sec": 1, "type": "english"},
                     {"item": "x", "start_price": 100_000_001, "duration_sec": 1, "type": "english"},
                     {"item": "x", "start_price": 1.5, "duration_sec": 1, "type": "english"},
                     {"item": "x", "start_price": 1, "duration_sec": 3601, "type": "english"},
                     {"item": "x", "start_price": 1, "duration_sec": 10, "type": "nope"}):
            s, b, _ = http(self.app, "POST", "/api/auctions", body)
            self.assertEqual(s, 400, body)
        aid = http(self.app, "POST", "/api/auctions",
                   {"item": "x", "start_price": 10, "duration_sec": 30, "type": "english"})[1]["auction"]["id"]
        s, b, _ = http(self.app, "POST", f"/api/auctions/{aid}/bids", {"bidder": "   ", "amount": 10})
        self.assertEqual(s, 400)
        s, b, _ = http(self.app, "POST", f"/api/auctions/{aid}/bids", {"bidder": "x" * 21, "amount": 10})
        self.assertEqual(s, 400)

    def test_list(self):
        http(self.app, "POST", "/api/auctions",
             {"item": "a", "start_price": 10, "duration_sec": 30, "type": "dutch"})
        s, b, _ = http(self.app, "GET", "/api/auctions")
        self.assertEqual(s, 200)
        self.assertEqual(len(b["auctions"]), 1)
        self.assertIn(b["auctions"][0]["current_price"], (9, 10))


if __name__ == "__main__":
    unittest.main()
