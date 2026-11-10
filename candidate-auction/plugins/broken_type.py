"""시연용: validate_bid 에서 예외를 낸다(장애 격리 시연). 기본 미적재."""
from kernel import contract

MANIFEST = {
    "name": "broken_type",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "시연용 고장 방식: 입찰하면 예외(3회면 disabled)",
    "autoload": False,
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        bids = payload["bids"]
        if op == "validate_bid":
            raise RuntimeError("시연용 고장")
        if op == "view":
            return {"price": None, "visible_bids": [], "bid_count": len(bids)}
        if op == "on_bid_accepted":
            return {"close_now": False, "outbid": None}
        if op == "settle":
            return {"winner": None, "price": None}
        raise contract.Rejected(f"모르는 op: {op}")
