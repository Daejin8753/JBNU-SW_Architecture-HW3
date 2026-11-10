"""시험용 멈추는 fixture(별도 프로세스 notifier). item 이 hang 이면 응답 안 함, slow 면 1초 뒤."""
import time

from kernel import contract

MANIFEST = {
    "name": "hang_notifier",
    "kind": "notifier",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "시험용 멈추는 notifier",
    "runtime": "process",
    "timeout_sec": 3,
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        item = payload["item"]
        if item == "hang":
            while True:
                time.sleep(60)
        if item == "slow":
            time.sleep(1)
        return {"notifications": [{"user": payload["user"], "message": item}]}
