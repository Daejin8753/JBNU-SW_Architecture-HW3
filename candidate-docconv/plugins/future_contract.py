"""시연용: 계약 2.0 을 요구하는 플러그인. 코어(1.0)는 rejected 로 둔다."""
from kernel import contract

MANIFEST = {
    "name": "future_contract",
    "kind": "converter",
    "contract": "2.0",
    "version": "0.1.0",
    "description": "미래 계약 버전 시연(적재 거부되어야 함)",
    "formats": ["future"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
