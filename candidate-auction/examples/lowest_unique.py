"""예제: 최저 유일가 경매. plugins/ 에 복사하고 [다시 검색] → [설치] 해 본다."""
from kernel import contract

MANIFEST = {
    "name": "lowest_unique",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "최저 유일가: 한 사람만 낸 금액 중 가장 낮은 금액이 낙찰(1인 3회)",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        bids = payload["bids"]
        if op == "validate_bid":
            bid = payload["bid"]
            amount = bid["amount"]
            if not isinstance(amount, int) or amount < 1:
                raise contract.Rejected("금액은 1원 이상")
            if sum(1 for b in bids if b["bidder"] == bid["bidder"]) >= 3:
                raise contract.Rejected("1인 최대 3회입니다")
            return {"amount": amount}
        if op == "view":
            return {"price": None, "visible_bids": [], "bid_count": len(bids)}
        if op == "on_bid_accepted":
            return {"close_now": False, "outbid": None}
        if op == "settle":
            who = {}
            for b in bids:
                who.setdefault(b["amount"], set()).add(b["bidder"])
            unique = sorted(amt for amt, people in who.items() if len(people) == 1)
            if not unique:
                return {"winner": None, "price": None}
            low = unique[0]
            return {"winner": next(iter(who[low])), "price": low}
        raise contract.Rejected(f"모르는 op: {op}")
