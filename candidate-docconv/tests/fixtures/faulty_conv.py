"""시험용: filename 이 reject 면 Rejected, 그 밖에는 예외."""
from kernel import contract

MANIFEST = {
    "name": "faulty_conv",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "formats": ["faultfmt"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        if payload["filename"] == "reject":
            raise contract.Rejected("시험용 거부")
        if payload["filename"] == "ok":
            return {"markdown": "ok", "meta": {}}
        raise ValueError("시험용 결함")
