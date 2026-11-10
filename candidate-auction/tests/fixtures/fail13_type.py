"""시험용: 금액 13 이면 validate_bid 에서 예외. 금액 7 이면 Rejected. 그 밖은 단순 최고가."""
from kernel import contract

MANIFEST = {
    "name": "fail13_type",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "시험용 고장 방식",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        bids = payload["bids"]
        if op == "validate_bid":
            amount = payload["bid"]["amount"]
            if amount == 13:
                raise RuntimeError("13 은 고장")
            if amount == 7:
                raise contract.Rejected("7 은 거부")
            return {"amount": amount}
        if op == "view":
            return {"price": None, "visible_bids": [], "bid_count": len(bids)}
        if op == "on_bid_accepted":
            return {"close_now": False, "outbid": None}
        if op == "settle":
            if not bids:
                return {"winner": None, "price": None}
            top = max(bids, key=lambda b: b["amount"])
            return {"winner": top["bidder"], "price": top["amount"]}
        raise contract.Rejected(op)
