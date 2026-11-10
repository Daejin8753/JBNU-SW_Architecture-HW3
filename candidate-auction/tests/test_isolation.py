"""E3 장애 격리, E8 동시성(별도 프로세스 어댑터)."""
import threading
import time
import unittest

from helpers import Env, bid, make_auction, wait_until

from kernel.kernel import CallError

NAME = "hang_notifier"


def outbid(item):
    return {"auction_id": "a1", "item": item, "user": "u", "new_price": 10}


class E3IsolationTest(unittest.TestCase):
    def test_rejected_and_faults(self):
        env = Env(plugins=("english",), fixtures=("fail13_type",))
        try:
            app = env.app()
            k = app.kernel
            aid = make_auction(app, "fail13_type", duration_sec=600)
            for _ in range(10):
                with self.assertRaises(CallError) as c:
                    bid(app, aid, "갑", 7)
                self.assertEqual(c.exception.code, "rejected")
            self.assertEqual(k.plugin_info("fail13_type")["state"], "active")
            self.assertEqual(k.plugin_info("fail13_type")["failures"], 0)
            for i in range(3):
                with self.assertRaises(CallError) as c:
                    bid(app, aid, "갑", 13)
                self.assertEqual(c.exception.code, "fault")
            info = k.plugin_info("fail13_type")
            self.assertEqual(info["state"], "disabled")
            self.assertIn("연속 3회", info["reason"])
            with self.assertRaises(CallError) as c:
                bid(app, aid, "갑", 5)
            self.assertEqual(c.exception.code, "unavailable")
            # 코어와 다른 플러그인은 계속 응답한다
            eid = make_auction(app, "english")
            self.assertEqual(bid(app, eid, "을", 1000)["bid"]["amount"], 1000)
            self.assertEqual(len(app.flow.list_auctions()["auctions"]), 2)
            k.install("fail13_type")  # 다시 켜기
            self.assertEqual(k.plugin_info("fail13_type")["state"], "active")
            self.assertEqual(bid(app, aid, "갑", 5)["bid"]["amount"], 5)
        finally:
            env.close()

    def test_success_resets_failures(self):
        env = Env(plugins=(), fixtures=("fail13_type",))
        try:
            app = env.app()
            aid = make_auction(app, "fail13_type", duration_sec=600)
            for _ in range(2):
                with self.assertRaises(CallError):
                    bid(app, aid, "갑", 13)
            bid(app, aid, "갑", 5)
            self.assertEqual(app.kernel.plugin_info("fail13_type")["failures"], 0)
        finally:
            env.close()

    def test_hang_process_timeout_then_restart(self):
        env = Env(plugins=(), fixtures=(NAME,))
        try:
            k = env.app().kernel
            pid1 = k.instance_of(NAME).pid
            t0 = time.monotonic()
            with self.assertRaises(CallError) as c:
                k.call(NAME, "on_outbid", outbid("hang"))
            took = time.monotonic() - t0
            self.assertEqual(c.exception.code, "fault")
            self.assertLess(took, 6.0)
            self.assertGreaterEqual(took, 2.9)
            self.assertIsNone(k.instance_of(NAME).pid)  # 자식 정리됨
            r = k.call(NAME, "on_outbid", outbid("ok"))
            self.assertEqual(r["notifications"][0]["message"], "ok")
            self.assertNotEqual(k.instance_of(NAME).pid, pid1)
            self.assertEqual(k.plugin_info(NAME)["failures"], 0)
        finally:
            env.close()

    def test_process_ready_false_rejected(self):
        env = Env(plugins=(), fixtures=("ok_requires",))
        try:
            info = env.app().kernel.plugin_info("ok_requires")
            self.assertEqual(info["state"], "rejected")
            self.assertIn("준비 실패", info["reason"])
        finally:
            env.close()


class E8ConcurrencyTest(unittest.TestCase):
    def test_concurrent_and_busy(self):
        env = Env(plugins=(), fixtures=(NAME,))
        try:
            k = env.app().kernel
            # 서로 다른 일반 입력 10개 동시 → 모두 성공, 각자 자기 입력
            results, errors = {}, []

            def one(i):
                try:
                    r = k.call(NAME, "on_outbid", outbid(f"item{i}"))
                    results[i] = r["notifications"][0]["message"]
                except Exception as e:
                    errors.append(e)
            ts = [threading.Thread(target=one, args=(i,)) for i in range(10)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(10)
            self.assertEqual(errors, [])
            self.assertEqual(results, {i: f"item{i}" for i in range(10)})

            adapter = k.instance_of(NAME)
            hang = {}

            def run_hang():
                t0 = time.monotonic()
                try:
                    k.call(NAME, "on_outbid", outbid("hang"))
                    hang["code"] = "ok"
                except CallError as e:
                    hang["code"] = e.code
                hang["took"] = time.monotonic() - t0
            th = threading.Thread(target=run_hang)
            th.start()
            self.assertTrue(wait_until(lambda: adapter.busy, 2.0), "busy 가 2초 안에 참이 되지 않음")

            normal = {}

            def run_normal(i):
                t0 = time.monotonic()
                try:
                    r = k.call(NAME, "on_outbid", outbid(f"n{i}"))
                    normal[i] = ("ok", r["notifications"][0]["message"])
                except CallError as e:
                    normal[i] = (e.code, None)
                normal[f"took{i}"] = time.monotonic() - t0
            ns = [threading.Thread(target=run_normal, args=(i,)) for i in range(2)]
            for t in ns:
                t.start()
            th.join(10)
            for t in ns:
                t.join(10)
            self.assertEqual(hang["code"], "fault")
            self.assertLess(hang["took"], 6.0)
            for i in range(2):
                code, msg = normal[i]
                self.assertIn(code, ("ok", "busy"))
                if code == "ok":
                    self.assertEqual(msg, f"n{i}")
                self.assertLess(normal[f"took{i}"], 9.0)
            self.assertEqual(k.plugin_info(NAME)["state"], "active")
            r = k.call(NAME, "on_outbid", outbid("after"))
            self.assertEqual(r["notifications"][0]["message"], "after")
            self.assertEqual(k.plugin_info(NAME)["failures"], 0)
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
