"""시험용: 알림을 만들다 예외를 낸다."""
from kernel import contract

MANIFEST = {
    "name": "raise_notifier",
    "kind": "notifier",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "고장 난 알림",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        raise RuntimeError("알림 고장")
