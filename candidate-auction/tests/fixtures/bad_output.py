"""시험용: validate_bid 출력이 계약 위반(amount 가 문자열)."""
from kernel import contract

MANIFEST = {
    "name": "bad_output",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "출력 계약 위반",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        if op == "validate_bid":
            return {"amount": "많이"}
        if op == "view":
            return {"price": None, "visible_bids": [], "bid_count": 0}
        raise contract.Rejected(op)
