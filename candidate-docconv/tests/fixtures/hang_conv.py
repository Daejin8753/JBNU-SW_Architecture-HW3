"""시험용 멈추는 fixture(별도 프로세스). filename 이 hang 이면 응답하지 않고, slow 면 1초 뒤 응답한다."""
import time

from kernel import contract

MANIFEST = {
    "name": "hang_conv",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "runtime": "process",
    "timeout_sec": 3,
    "formats": ["hangfmt"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        name = payload["filename"]
        if name == "hang":
            time.sleep(3600)
        elif name == "slow":
            time.sleep(1)
        return {"markdown": f"{name}:{len(payload['data'])}", "meta": {"filename": name}}
