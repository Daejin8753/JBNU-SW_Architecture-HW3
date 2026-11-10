"""E1 확장, E2 제거, E4 계약 위반, E6 보존."""
import json
import os
import threading
import unittest

from helpers import EXAMPLES, Env, bid, http, make_auction, wait_until

from kernel.kernel import CallError


def outbid(item):
    return {"auction_id": "a1", "item": item, "user": "u", "new_price": 10}


class E1ExtendTest(unittest.TestCase):
    def test_new_plugin_without_restart(self):
        env = Env()
        try:
            app = env.app().start_background()
            s, b, _ = http(app, "POST", "/api/auctions",
                           {"item": "x", "start_price": 10, "duration_sec": 30, "type": "lowest_unique"})
            self.assertEqual(s, 400)  # 아직 모르는 방식
            env.add(os.path.join(EXAMPLES, "lowest_unique.py"))
            s, b, _ = http(app, "POST", "/api/plugins/rescan")
            self.assertEqual(s, 200)
            states = {p["name"]: p["state"] for p in b["plugins"]}
            self.assertEqual(states["lowest_unique"], "available")
            s, b, _ = http(app, "POST", "/api/plugins/lowest_unique/install")
            self.assertEqual((s, b["plugin"]["state"]), (200, "active"))
            s, b, _ = http(app, "POST", "/api/auctions",
                           {"item": "x", "start_price": 10, "duration_sec": 30, "type": "lowest_unique"})
            self.assertEqual(s, 200, b)
            aid = b["auction"]["id"]
            s, b, _ = http(app, "POST", f"/api/auctions/{aid}/bids", {"bidder": "갑", "amount": 3})
            self.assertEqual(s, 200, b)
            self.assertEqual(b["auction"]["bid_count"], 1)
        finally:
            env.close()


class E2RemoveTest(unittest.TestCase):
    def test_remove_blocks_only_that_plugin(self):
        env = Env()
        try:
            app = env.app()
            app.kernel.remove("english")
            with self.assertRaises(CallError) as c:
                make_auction(app, "english")
            self.assertEqual(c.exception.code, "rejected")
            with self.assertRaises(CallError) as c:
                app.kernel.call("english", "settle", {"auction": {}, "bids": []})
            self.assertEqual(c.exception.code, "unavailable")
            aid = make_auction(app, "dutch")
            self.assertEqual(bid(app, aid, "갑")["auction"]["status"], "closed")
        finally:
            env.close()

    def test_remove_during_slow_call(self):
        env = Env(plugins=(), fixtures=("hang_notifier",))
        try:
            k = env.app().kernel
            name = "hang_notifier"
            pid1 = k.instance_of(name).pid
            out = {}
            t = threading.Thread(target=lambda: out.update(r=k.call(name, "on_outbid", outbid("slow"))))
            t.start()
            self.assertTrue(wait_until(lambda: k.registry.get(name).inflight == 1, 2))
            k.remove(name)
            with self.assertRaises(CallError) as c:
                k.call(name, "on_outbid", outbid("x"))
            self.assertEqual(c.exception.code, "unavailable")
            with self.assertRaises(CallError) as c:
                k.install(name)
            self.assertEqual(c.exception.code, "conflict")
            t.join(5)
            self.assertEqual(out["r"]["notifications"][0]["message"], "slow")  # 끝까지 성공
            self.assertTrue(wait_until(lambda: k.instance_of(name) is None, 2))  # 정리됨
            k.install(name)
            r = k.call(name, "on_outbid", outbid("again"))
            self.assertEqual(r["notifications"][0]["message"], "again")
            self.assertNotEqual(k.instance_of(name).pid, pid1)  # 새 자식
        finally:
            env.close()

    def test_remove_refused_while_auction_uses_type(self):
        env = Env()
        try:
            app = env.app()
            make_auction(app, "english")
            with self.assertRaises(CallError) as c:
                app.kernel.remove("english")
            self.assertEqual(c.exception.code, "conflict")
            self.assertEqual(app.kernel.plugin_info("english")["state"], "active")
        finally:
            env.close()


class E4ContractTest(unittest.TestCase):
    def test_contract_violations(self):
        env = Env(plugins=("english", "future_contract"),
                  fixtures=("contract_v2", "no_handle", "load_error", "syntax_error", "bad_output"))
        try:
            app = env.app()
            k = app.kernel
            info = {p["name"]: p for p in k.list_plugins()}
            self.assertEqual(info["contract_v2"]["state"], "rejected")
            self.assertIn("계약 버전", info["contract_v2"]["reason"])
            self.assertEqual(info["future_contract"]["state"], "rejected")
            self.assertEqual(info["no_handle"]["state"], "rejected")
            self.assertIn("handle", info["no_handle"]["reason"])
            self.assertEqual(info["load_error"]["state"], "rejected")
            self.assertIn("적재 중 예외", info["load_error"]["reason"])
            self.assertEqual(info["syntax_error"]["state"], "rejected")
            self.assertEqual(info["english"]["state"], "active")  # 나머지는 정상
            self.assertEqual(info["bad_output"]["state"], "active")
            aid = make_auction(app, "bad_output")
            with self.assertRaises(CallError) as c:
                bid(app, aid, "갑", 10)
            self.assertEqual(c.exception.code, "fault")
            self.assertIn("출력 계약 위반", c.exception.message)
            self.assertEqual(k.plugin_info("bad_output")["failures"], 1)
            self.assertEqual(len(app.flow.get_auction(aid)["auction"]["visible_bids"]), 0)
        finally:
            env.close()

    def test_input_contract(self):
        env = Env(plugins=("english",))
        try:
            k = env.app().kernel
            with self.assertRaises(CallError) as c:
                k.call("english", "settle", {"auction": {}})
            self.assertEqual(c.exception.code, "rejected")
            self.assertEqual(k.plugin_info("english")["failures"], 0)
        finally:
            env.close()


class E6PersistTest(unittest.TestCase):
    def test_restart_keeps_data_and_states(self):
        env = Env(plugins=("english", "outbid_notifier"), fixtures=("fail13_type",))
        try:
            app = env.app()
            aid = make_auction(app, "english", duration_sec=600)
            bid(app, aid, "갑", 1000)
            fid = make_auction(app, "fail13_type", duration_sec=600)
            for _ in range(3):
                with self.assertRaises(CallError):
                    bid(app, fid, "갑", 13)
            reason = app.kernel.plugin_info("fail13_type")["reason"]
            self.assertEqual(app.kernel.plugin_info("fail13_type")["state"], "disabled")
            app.stop()
            with open(os.path.join(env.data, "plugins.json"), encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["fail13_type"], {"state": "disabled", "reason": reason})

            app2 = env.app()
            info = app2.kernel.plugin_info("fail13_type")
            self.assertEqual((info["state"], info["reason"]), ("disabled", reason))
            self.assertEqual(app2.kernel.plugin_info("english")["state"], "active")
            a = app2.flow.get_auction(aid)["auction"]
            self.assertEqual(a["status"], "open")
            self.assertEqual([b["amount"] for b in a["visible_bids"]], [1000])
            app2.kernel.install("fail13_type")  # 다시 켜기로만 복구
            self.assertEqual(app2.kernel.plugin_info("fail13_type")["state"], "active")
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
