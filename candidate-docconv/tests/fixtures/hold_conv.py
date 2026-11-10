"""시험용 붙잡는 fixture: hang_conv 와 같은 코드, 이름과 timeout_sec(10) 만 다르다(E3 shutdown (가))."""
import time

from kernel import contract

MANIFEST = {
    "name": "hold_conv",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "runtime": "process",
    "timeout_sec": 10,
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
