"""네 방식(예제 포함)의 입찰 조건, 낙찰 규칙, 동률, 유찰."""
import json
import os
import unittest

from helpers import EXAMPLES, Env, bid, make_auction

from kernel.kernel import CallError


class RulesBase(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.env.add(os.path.join(EXAMPLES, "lowest_unique.py"))
        self.app = self.env.app()

    def tearDown(self):
        self.env.close()

    def rejected(self, aid, who, amount=None):
        with self.assertRaises(CallError) as c:
            bid(self.app, aid, who, amount)
        self.assertEqual(c.exception.code, "rejected", c.exception.message)
        return c.exception.message

    def close(self, aid):
        self.app.flow.close_due(aid)
        return self.app.flow.get_auction(aid)["auction"]


class EnglishTest(RulesBase):
    def test_rules(self):
        aid = make_auction(self.app, "english", start_price=1000)
        self.rejected(aid, "갑", 999)
        self.rejected(aid, "갑")              # 금액 없음
        bid(self.app, aid, "갑", 1000)
        self.rejected(aid, "갑", 2000)        # 현재 최고 입찰자
        self.rejected(aid, "을", 1049)        # 증가액 50
        r = bid(self.app, aid, "을", 1050)
        self.assertEqual(r["auction"]["current_price"], 1050)
        self.assertEqual(len(r["auction"]["visible_bids"]), 2)
        a = self.close(aid)
        self.assertEqual((a["status"], a["winner"], a["price"]), ("closed", "을", 1050))

    def test_small_start_increment_is_one(self):
        aid = make_auction(self.app, "english", start_price=10)
        bid(self.app, aid, "갑", 10)
        bid(self.app, aid, "을", 11)

    def test_unsold(self):
        a = self.close(make_auction(self.app, "english"))
        self.assertEqual((a["status"], a["winner"], a["price"]), ("closed", None, None))


class SealedTest(RulesBase):
    def test_second_price_and_tie(self):
        aid = make_auction(self.app, "sealed_second", start_price=100)
        self.rejected(aid, "갑", 99)
        bid(self.app, aid, "갑", 500)
        self.rejected(aid, "갑", 600)         # 1인 1회
        bid(self.app, aid, "을", 500)          # 동률, 늦게 냄
        bid(self.app, aid, "병", 300)
        a = self.close(aid)
        self.assertEqual((a["winner"], a["price"]), ("갑", 500))

    def test_second_price(self):
        aid = make_auction(self.app, "sealed_second", start_price=100)
        bid(self.app, aid, "갑", 300)
        bid(self.app, aid, "을", 900)
        a = self.close(aid)
        self.assertEqual((a["winner"], a["price"]), ("을", 300))

    def test_single_bid_pays_start(self):
        aid = make_auction(self.app, "sealed_second", start_price=100)
        bid(self.app, aid, "갑", 900)
        a = self.close(aid)
        self.assertEqual((a["winner"], a["price"]), ("갑", 100))

    def test_unsold(self):
        a = self.close(make_auction(self.app, "sealed_second"))
        self.assertEqual((a["winner"], a["price"]), (None, None))


class DutchTest(RulesBase):
    def test_price_formula(self):
        auction = {"id": "x", "item": "x", "start_price": 1000, "duration_sec": 100,
                   "type": "dutch", "status": "open", "created_at": 0.0, "ends_at": 100.0}
        k = self.app.kernel

        def price(now):
            return k.call("dutch", "view", {"auction": auction, "bids": [], "now": now})["price"]
        self.assertEqual(price(0.0), 1000)
        self.assertEqual(price(50.0), 650)      # 1000 - 700*0.5
        self.assertEqual(price(33.3), 766)      # floor(766.9)
        self.assertEqual(price(100.0), 300)     # 바닥가 ceil(300)
        self.assertEqual(price(500.0), 300)

    def test_first_accept_wins_immediately(self):
        aid = make_auction(self.app, "dutch", start_price=1000, duration_sec=3600)
        r = bid(self.app, aid, "갑", 1)          # 금액은 무시, 현재가로 확정
        self.assertEqual(r["auction"]["status"], "closed")
        self.assertEqual(r["auction"]["winner"], "갑")
        self.assertIn(r["bid"]["amount"], (999, 1000))
        with self.assertRaises(CallError) as c:
            bid(self.app, aid, "을")
        self.assertEqual(c.exception.code, "conflict")

    def test_unsold(self):
        a = self.close(make_auction(self.app, "dutch"))
        self.assertEqual((a["status"], a["winner"]), ("closed", None))


class LowestUniqueTest(RulesBase):
    def test_rules(self):
        aid = make_auction(self.app, "lowest_unique", start_price=100)
        self.rejected(aid, "갑", 0)
        for amt in (1, 2, 5):
            bid(self.app, aid, "갑", amt)
        self.rejected(aid, "갑", 6)            # 1인 3회
        bid(self.app, aid, "을", 1)
        bid(self.app, aid, "을", 2)
        bid(self.app, aid, "병", 4)
        a = self.close(aid)                      # 1·2 는 중복, 4(병)·5(갑) 유일 → 4
        self.assertEqual((a["winner"], a["price"]), ("병", 4))

    def test_no_unique_unsold(self):
        aid = make_auction(self.app, "lowest_unique")
        bid(self.app, aid, "갑", 3)
        bid(self.app, aid, "을", 3)
        a = self.close(aid)
        self.assertEqual((a["winner"], a["price"]), (None, None))

    def test_private_before_close(self):
        aid = make_auction(self.app, "lowest_unique")
        r = bid(self.app, aid, "숨은갑", 4321)
        txt = json.dumps([r["auction"], self.app.flow.list_auctions()], ensure_ascii=False)
        self.assertNotIn("숨은갑", txt)
        self.assertNotIn(": 4321", txt)
        self.assertEqual(r["auction"]["bid_count"], 1)
        a = self.close(aid)                      # 마감 뒤에는 공개
        self.assertEqual(a["winner"], "숨은갑")


if __name__ == "__main__":
    unittest.main()
