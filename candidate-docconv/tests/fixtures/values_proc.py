"""시험용 fixture: 값 왕복·출력 값 위반(process). values_inproc 와 같은 코드"""
from kernel import contract

MANIFEST = {
    "name": "values_proc",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "runtime": "process",
    "formats": ["valproc"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        case = payload["filename"]
        cases = {
            "tuple": {"v": (1, 2)},
            "intkey": {"v": {1: "x"}},
            "bigint": {"v": 2**63},
            "nan": {"v": float("nan")},
            "edge": {"max": 2**63 - 1, "min": -2**63},
            "esc": {"a": {"$b64": "YQ=="}, "b": {"$esc": 1}},
            "bytes": {"data": payload["data"], "members": payload["members"]},
        }
        return {"markdown": case, "meta": cases.get(case, {})}
