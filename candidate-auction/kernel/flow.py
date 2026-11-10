"""코어의 도메인 절차: 경매 생성 → 진행 → 마감 → 정산, 경매별 잠금.

플러그인·내부 서버 호출은 모두 kernel.py 를 거친다.
"""
import secrets
import threading
import time

from kernel.contract import type_ok
from kernel.kernel import CallError
from kernel.trace import hop

TYPE_KIND = "auction_type"
NOTIFIER_KIND = "notifier"
AUCTION_KEYS = ("id", "item", "start_price", "duration_sec", "type", "status",
                "created_at", "ends_at")


class Reply:
    """응답 본문과, 응답을 보낸 뒤에 할 일(SSE 이벤트 넣기)."""

    def __init__(self, body, after=None):
        self.body = body
        self.after = after


def _auction_view(a):
    return {k: a[k] for k in AUCTION_KEYS}


def _bid_view(b):
    return {"id": b["id"], "bidder": b["bidder"], "amount": b["amount"],
            "created_at": b["created_at"]}


def _bad(msg):
    return CallError("rejected", msg)


class AuctionFlow:
    def __init__(self, kernel, tracer):
        self.k = kernel
        self.tracer = tracer
        self._locks = {}
        self._locks_guard = threading.Lock()
        kernel.add_remove_guard(self._remove_guard)
        kernel.add_activate_hook(self._on_activated)

    # ---- 보조 ----
    def _st(self, op, **args):
        return self.k.internal("storage", op, **args)

    def _lock(self, auction_id):
        with self._locks_guard:
            return self._locks.setdefault(auction_id, threading.Lock())

    def _call_type(self, a, op, payload):
        return self.k.call(a["type"], op, payload, kind=TYPE_KIND)

    def public(self, a, bids, now=None):
        """밖으로 보내는 경매 정보. 마감 전에는 view 결과만 싣는다."""
        out = dict(_auction_view(a), winner=a.get("winner"), price=a.get("price"),
                   reason=a.get("reason") or "", closed_at=a.get("closed_at"))
        if a["status"] == "closed":
            out.update(current_price=a.get("price"),
                       visible_bids=[_bid_view(b) for b in bids], bid_count=len(bids))
            return out
        out["winner"] = out["price"] = None
        try:
            v = self._call_type(a, "view", {"auction": _auction_view(a),
                                            "bids": [_bid_view(b) for b in bids],
                                            "now": now if now is not None else time.time()})
            out.update(current_price=v["price"], visible_bids=v["visible_bids"],
                       bid_count=v["bid_count"])
        except CallError as e:
            out.update(current_price=None, visible_bids=[], bid_count=len(bids),
                       view_error=e.message)
        return out

    def _settle_locked(self, a, bids):
        """경매 잠금을 잡은 쪽만 부른다. 상태 변경을 돌려주고 저장하지 않는다."""
        try:
            r = self._call_type(a, "settle", {"auction": _auction_view(a),
                                              "bids": [_bid_view(b) for b in bids]})
            return {"status": "closed", "winner": r["winner"], "price": r["price"],
                    "reason": "", "closed_at": time.time()}
        except CallError as e:
            return {"status": "settle_pending", "reason": e.message}

    # ---- 시작 ----
    def start(self):
        """open 경매를 다시 예약하고 이미 지난 것은 바로 마감한다."""
        now = time.time()
        for a in self._st("auctions_by_status", statuses=["open"]):
            if a["ends_at"] <= now:
                self.close_due(a["id"])
            else:
                self.k.internal("clock", "schedule", auction_id=a["id"], ends_at=a["ends_at"])

    # ---- 조회 ----
    def list_auctions(self):
        now = time.time()
        return {"auctions": [self.public(a, self._st("list_bids", auction_id=a["id"]), now)
                             for a in self._st("list_auctions")]}

    def get_auction(self, auction_id):
        a = self._st("get_auction", auction_id=auction_id)
        if a is None:
            raise CallError("not_found", "경매 없음")
        return {"auction": self.public(a, self._st("list_bids", auction_id=auction_id))}

    def notifications(self, user):
        user = (user or "").strip()
        if not 1 <= len(user) <= 20:
            raise _bad("사용자 이름은 1~20자")
        return {"notifications": self._st("list_notifications", user=user)}

    # ---- 생성 ----
    def create_auction(self, body):
        item = body.get("item")
        if not isinstance(item, str) or not 1 <= len(item.strip()) <= 100:
            raise _bad("물품명은 1~100자")
        start_price = body.get("start_price")
        if not type_ok(start_price, int) or not 1 <= start_price <= 100_000_000:
            raise _bad("시작가는 1~100,000,000 원 정수")
        duration = body.get("duration_sec")
        if not type_ok(duration, int) or not 1 <= duration <= 3600:
            raise _bad("진행 시간은 1~3600초 정수")
        type_name = body.get("type")
        if type_name not in self.k.active_names(TYPE_KIND):
            raise _bad("사용할 수 있는 경매 방식이 아님")
        now = time.time()
        a = {"id": secrets.token_hex(6), "item": item.strip(), "start_price": start_price,
             "duration_sec": duration, "type": type_name, "status": "open",
             "created_at": now, "ends_at": now + duration}
        self._st("create_auction", auction=a)
        self.k.internal("clock", "schedule", auction_id=a["id"], ends_at=a["ends_at"])
        view = self.public(a, [], now)
        return Reply({"auction": view},
                     lambda: self.k.events.publish("auction_created", view))

    # ---- 입찰 ----
    def place_bid(self, auction_id, body):
        bidder = body.get("bidder")
        bidder = bidder.strip() if isinstance(bidder, str) else ""
        if not 1 <= len(bidder) <= 20:
            raise _bad("입찰자 이름은 1~20자")
        amount = body.get("amount")
        if amount is not None and not type_ok(amount, int):
            raise _bad("금액은 정수")

        with self._lock(auction_id):
            a = self._st("get_auction", auction_id=auction_id)
            if a is None:
                raise CallError("not_found", "경매 없음")
            now = time.time()
            if a["status"] != "open" or now >= a["ends_at"]:
                raise CallError("conflict", "마감된 경매")
            bids = [_bid_view(b) for b in self._st("list_bids", auction_id=auction_id)]
            bid = {"id": f"{auction_id}_{len(bids) + 1:05d}", "bidder": bidder,
                   "amount": amount, "created_at": now}
            r = self._call_type(a, "validate_bid", {"auction": _auction_view(a), "bids": bids,
                                                    "bid": dict(bid), "now": now})
            bid["amount"] = r["amount"]
            all_bids = bids + [bid]
            r2 = self._call_type(a, "on_bid_accepted", {"auction": _auction_view(a),
                                                        "bids": all_bids, "bid": dict(bid)})
            change = self._settle_locked(a, all_bids) if r2["close_now"] else None
            self._st("save_bid", auction_id=auction_id, bid=bid, change=change)
            a.update(change or {})
            view = self.public(a, all_bids, now)
            outbid = r2["outbid"]

        # 알림은 잠금 밖. 장애는 notify_error 로 받아 둔다(선택 단계)
        notes, errors = [], []
        if outbid:
            for name in self.k.active_names(NOTIFIER_KIND):
                try:
                    res = self.k.call(name, "on_outbid", {
                        "auction_id": auction_id, "item": a["item"],
                        "user": outbid, "new_price": bid["amount"]}, kind=NOTIFIER_KIND)
                except CallError as e:
                    errors.append(f"{name}: {e.message}")
                    continue
                for n in res["notifications"]:
                    if isinstance(n, dict) and isinstance(n.get("user"), str) \
                            and isinstance(n.get("message"), str):
                        notes.append({"user": n["user"], "message": n["message"],
                                      "auction_id": auction_id, "created_at": time.time()})
            if notes:
                self._st("add_notifications", items=notes)

        def after():
            ev = self.k.events
            ev.publish("bid_accepted", view)
            for n in notes:
                ev.publish("notification", n)
            if change:
                ev.publish("auction_closed", view)

        return Reply({"bid": bid, "auction": view,
                      "notify_error": "; ".join(errors) or None}, after)

    # ---- 마감 ----
    def close_due(self, auction_id):
        """예약 마감. open 이 아니면 아무것도 하지 않는다(중복 마감 무해)."""
        with self.tracer.request(f"clock close {auction_id}"):
            with hop("internal:clock", "kernel", "close_due"):
                with self._lock(auction_id):
                    a = self._st("get_auction", auction_id=auction_id)
                    if a is None or a["status"] != "open":
                        return
                    bids = self._st("list_bids", auction_id=auction_id)
                    change = self._settle_locked(a, bids)
                    self._st("update_auction", auction_id=auction_id, change=change)
                    a.update(change)
                    view = self.public(a, bids)
        self.k.events.publish("auction_closed", view)

    def _on_activated(self, name, kind):
        """방식이 다시 active 가 되면 그 방식의 settle_pending 경매를 다시 정산한다."""
        if kind != TYPE_KIND:
            return
        for row in self._st("auctions_by_status", statuses=["settle_pending"], type_name=name):
            with self._lock(row["id"]):
                a = self._st("get_auction", auction_id=row["id"])
                if a["status"] != "settle_pending":
                    continue
                bids = self._st("list_bids", auction_id=a["id"])
                change = self._settle_locked(a, bids)
                self._st("update_auction", auction_id=a["id"], change=change)
                a.update(change)
                view = self.public(a, bids)
            self.k.events.publish("auction_closed", view)

    def _remove_guard(self, name):
        rows = self._st("auctions_by_status", statuses=["open", "settle_pending"], type_name=name)
        if rows:
            return f"진행 중이거나 정산 대기인 경매 {len(rows)}건이 이 방식을 씀"
        return None
