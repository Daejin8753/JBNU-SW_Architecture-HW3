"""코어 절차: 마감 시각, 재시작, 동시성, settle_pending, 알림 장애."""
import threading
import time
import unittest

from helpers import Env, bid, make_auction, wait_until

from kernel.kernel import CallError


def status(app, aid):
    return app.flow.get_auction(aid)["auction"]


class ClockTest(unittest.TestCase):
    def test_one_second_auction_closes_on_time(self):
        env = Env()
        try:
            app = env.app()
            aid = make_auction(app, "english", duration_sec=1)
            a0 = status(app, aid)
            self.assertTrue(wait_until(lambda: status(app, aid)["status"] == "closed", 3, 0.01))
            a = status(app, aid)
            self.assertLess(abs(a["closed_at"] - a0["ends_at"]), 0.5)
            # 예약이 없으면 timeout 없이 기다린다
            self.assertTrue(wait_until(lambda: app.clock.last_wait_timeout is None, 1))
            self.assertEqual(app.clock.pending(), 0)
        finally:
            env.close()

    def test_idle_clock_waits_without_timeout(self):
        env = Env()
        try:
            app = env.app()
            self.assertTrue(wait_until(lambda: app.clock.last_wait_timeout is None, 1))
            self.assertTrue(app.clock._thread.is_alive())
        finally:
            env.close()

    def test_restart_reschedules_and_closes_past(self):
        env = Env()
        try:
            app = env.app()
            past = make_auction(app, "english", duration_sec=1)
            later = make_auction(app, "english", duration_sec=3)
            bid(app, past, "갑", 1000)
            app.stop()
            time.sleep(1.2)
            app2 = env.app()
            self.assertEqual(status(app2, past)["status"], "closed")  # 시작 때 바로 마감
            self.assertEqual(status(app2, past)["winner"], "갑")
            self.assertEqual(status(app2, later)["status"], "open")
            self.assertEqual(app2.clock.pending(), 1)                 # 다시 예약됨
            self.assertTrue(wait_until(lambda: status(app2, later)["status"] == "closed", 3))
        finally:
            env.close()


class ConcurrencyTest(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.app = self.env.app()

    def tearDown(self):
        self.env.close()

    def run_parallel(self, fn, n):
        ok, codes = [], []
        barrier = threading.Barrier(n)

        def one(i):
            barrier.wait()
            try:
                ok.append(fn(i))
            except CallError as e:
                codes.append(e.code)
        ts = [threading.Thread(target=one, args=(i,)) for i in range(n)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(10)
        return ok, codes

    def test_english_same_amount(self):
        aid = make_auction(self.app, "english", start_price=1000)
        ok, codes = self.run_parallel(lambda i: bid(self.app, aid, f"u{i}", 1000), 20)
        self.assertEqual(len(ok), 1)
        self.assertEqual(codes, ["rejected"] * 19)
        self.assertEqual(status(self.app, aid)["bid_count"], 1)

    def test_dutch_concurrent_accept(self):
        aid = make_auction(self.app, "dutch", start_price=1000)
        ok, codes = self.run_parallel(lambda i: bid(self.app, aid, f"u{i}"), 10)
        self.assertEqual(len(ok), 1)
        self.assertTrue(all(c in ("conflict", "rejected") for c in codes))
        a = status(self.app, aid)
        self.assertEqual(a["status"], "closed")
        self.assertEqual(a["winner"], ok[0]["bid"]["bidder"])
        self.assertEqual(a["bid_count"], 1)

    def test_bid_after_close_rejected(self):
        aid = make_auction(self.app, "english", start_price=10, duration_sec=1)
        ends_at = status(self.app, aid)["ends_at"]
        amount, last_ok, conflict = 10, None, False
        i = 0
        while time.time() < ends_at + 1.0:
            i += 1
            try:
                r = bid(self.app, aid, f"u{i % 2}", amount)
                last_ok = r["bid"]
                amount += 1
            except CallError as e:
                if e.code == "conflict":
                    conflict = True
                    break
            time.sleep(0.005)
        self.assertTrue(conflict)
        self.assertTrue(wait_until(lambda: status(self.app, aid)["status"] == "closed", 2))
        a = status(self.app, aid)
        self.assertTrue(all(b["created_at"] < ends_at for b in a["visible_bids"]))
        self.assertEqual((a["winner"], a["price"]), (last_ok["bidder"], last_ok["amount"]))


class FaultFlowTest(unittest.TestCase):
    def test_settle_pending_then_reenable(self):
        env = Env(plugins=(), fixtures=("fail13_type",))
        try:
            app = env.app()
            aid = make_auction(app, "fail13_type", duration_sec=1)
            bid(app, aid, "갑", 50)
            for _ in range(3):
                with self.assertRaises(CallError):
                    bid(app, aid, "을", 13)
            self.assertEqual(app.kernel.plugin_info("fail13_type")["state"], "disabled")
            with self.assertRaises(CallError) as c:
                bid(app, aid, "을", 60)
            self.assertEqual(c.exception.code, "unavailable")      # 503
            self.assertTrue(wait_until(lambda: status(app, aid)["status"] == "settle_pending", 3))
            self.assertTrue(status(app, aid)["reason"])
            with self.assertRaises(CallError) as c:
                app.kernel.remove("fail13_type")                     # 정산 대기 경매가 씀
            self.assertEqual(c.exception.code, "conflict")
            app.kernel.install("fail13_type")
            a = status(app, aid)
            self.assertEqual((a["status"], a["winner"], a["price"]), ("closed", "갑", 50))
        finally:
            env.close()

    def test_notifier_fault_does_not_break_bid(self):
        env = Env(plugins=("english",), fixtures=("raise_notifier",))
        try:
            app = env.app()
            aid = make_auction(app, "english", start_price=100)
            bid(app, aid, "갑", 100)
            r = bid(app, aid, "을", 200)
            self.assertIn("raise_notifier", r["notify_error"])
            self.assertEqual(status(app, aid)["current_price"], 200)  # 입찰은 확정
            self.assertEqual(app.kernel.plugin_info("raise_notifier")["failures"], 1)
            self.assertEqual(app.kernel.plugin_info("english")["failures"], 0)
        finally:
            env.close()

    def test_ctx_only_allowed(self):
        env = Env(plugins=("english",))
        try:
            app = env.app()
            from kernel.context import Context
            ctx = Context(lambda s, o, a: app.kernel._ctx_call("english", s, o, a))
            ctx.log("허용")
            with self.assertRaises(PermissionError):
                ctx.internal("storage", "list_auctions")
            self.assertFalse(hasattr(ctx, "kernel"))
            self.assertEqual(app.audit.tail(1)[0]["source"], "english")
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
