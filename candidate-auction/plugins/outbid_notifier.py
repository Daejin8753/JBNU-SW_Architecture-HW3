"""밀려난 사람에게 줄 알림 문장을 만든다. 별도 프로세스에서 돈다."""
from kernel import contract

MANIFEST = {
    "name": "outbid_notifier",
    "kind": "notifier",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "최고 입찰에서 밀린 사람에게 알림 문장 생성(별도 프로세스)",
    "runtime": "process",
    "timeout_sec": 3,
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        if op != "on_outbid":
            raise contract.Rejected(f"모르는 op: {op}")
        msg = (f"[{payload['item']}] 경매에서 다른 사람이 "
               f"{payload['new_price']:,}원으로 더 높게 입찰했습니다.")
        return {"notifications": [{"user": payload["user"], "message": msg}]}
