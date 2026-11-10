"""시연용: 계약 2.0 을 요구한다 → 코어(1.0)가 rejected 로 둔다."""
from kernel import contract

MANIFEST = {
    "name": "future_contract",
    "kind": "auction_type",
    "contract": "2.0",
    "version": "0.1.0",
    "description": "시연용: 계약 major 불일치",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        raise contract.Rejected("쓰이지 않음")
