"""내림차순(dutch) 경매. 첫 수락이 바로 낙찰된다."""
import math

from kernel import contract

MANIFEST = {
    "name": "dutch",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "내림차순: 가격이 내려가고 첫 수락이 낙찰",
}


def current_price(a, now):
    start = a["start_price"]
    floor_price = math.ceil(start * 0.3)
    elapsed = max(now - a["created_at"], 0)
    price = math.floor(start - (start - floor_price) * elapsed / a["duration_sec"])
    return max(floor_price, price)


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        a, bids = payload["auction"], payload["bids"]
        if op == "validate_bid":
            if bids:
                raise contract.Rejected("이미 낙찰되었습니다")
            return {"amount": current_price(a, payload["now"])}
        if op == "view":
            return {"price": current_price(a, payload["now"]), "visible_bids": [],
                    "bid_count": len(bids)}
        if op == "on_bid_accepted":
            return {"close_now": True, "outbid": None}
        if op == "settle":
            if not bids:
                return {"winner": None, "price": None}
            return {"winner": bids[0]["bidder"], "price": bids[0]["amount"]}
        raise contract.Rejected(f"모르는 op: {op}")
