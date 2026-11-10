"""봉인 2차 가격(Vickrey) 경매. 마감 전에는 입찰 수만 공개한다."""
from kernel import contract

MANIFEST = {
    "name": "sealed_second",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "봉인 2차 가격: 1인 1회, 최고가 입찰자가 두 번째 금액으로 낙찰",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        a, bids = payload["auction"], payload["bids"]
        if op == "validate_bid":
            bid = payload["bid"]
            amount = bid["amount"]
            if not isinstance(amount, int):
                raise contract.Rejected("입찰 금액을 입력하세요")
            if any(b["bidder"] == bid["bidder"] for b in bids):
                raise contract.Rejected("봉인 입찰은 1인 1회입니다")
            if amount < a["start_price"]:
                raise contract.Rejected(f"시작가 {a['start_price']:,}원 이상")
            return {"amount": amount}
        if op == "view":
            return {"price": None, "visible_bids": [], "bid_count": len(bids)}
        if op == "on_bid_accepted":
            return {"close_now": False, "outbid": None}
        if op == "settle":
            if not bids:
                return {"winner": None, "price": None}
            # 금액 내림차순, 같으면 먼저 낸 순(bids 는 시간순)
            ranked = sorted(enumerate(bids), key=lambda x: (-x[1]["amount"], x[0]))
            winner = ranked[0][1]
            price = ranked[1][1]["amount"] if len(ranked) > 1 else a["start_price"]
            return {"winner": winner["bidder"], "price": price}
        raise contract.Rejected(f"모르는 op: {op}")
