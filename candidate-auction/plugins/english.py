"""오름차순(english) 경매."""
import math

from kernel import contract

MANIFEST = {
    "name": "english",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "오름차순: 모든 입찰 공개, 최고가 낙찰",
}


def _top(bids):
    # 최고가 입찰. 같은 금액이면 먼저 낸 것
    best = None
    for b in bids:
        if best is None or b["amount"] > best["amount"]:
            best = b
    return best


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        a, bids = payload["auction"], payload["bids"]
        if op == "validate_bid":
            bid = payload["bid"]
            amount = bid["amount"]
            if not isinstance(amount, int):
                raise contract.Rejected("입찰 금액을 입력하세요")
            top = _top(bids)
            if top is None:
                if amount < a["start_price"]:
                    raise contract.Rejected(f"첫 입찰은 시작가 {a['start_price']:,}원 이상")
            else:
                if bid["bidder"] == top["bidder"]:
                    raise contract.Rejected("이미 최고 입찰자입니다")
                step = max(1, math.ceil(a["start_price"] * 0.05))
                if amount < top["amount"] + step:
                    raise contract.Rejected(f"{top['amount'] + step:,}원 이상 입찰해야 합니다")
            return {"amount": amount}
        if op == "view":
            top = _top(bids)
            return {"price": top["amount"] if top else None,
                    "visible_bids": [{"bidder": b["bidder"], "amount": b["amount"],
                                      "created_at": b["created_at"]} for b in bids],
                    "bid_count": len(bids)}
        if op == "on_bid_accepted":
            bid = payload["bid"]
            prev = _top(bids[:-1])
            outbid = prev["bidder"] if prev and prev["bidder"] != bid["bidder"] else None
            if ctx is not None:
                ctx.log(f"english 입찰 수락 {a['id']} {bid['amount']}")
            return {"close_now": False, "outbid": outbid}
        if op == "settle":
            top = _top(bids)
            return {"winner": top["bidder"] if top else None,
                    "price": top["amount"] if top else None}
        raise contract.Rejected(f"모르는 op: {op}")
