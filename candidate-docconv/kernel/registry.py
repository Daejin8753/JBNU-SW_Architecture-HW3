"""레지스트리: 플러그인 이름 → 기록(계약, 접근 프로토콜, 상태)."""
import dataclasses
import json
import os
import threading

from kernel import contract


def _str(v):
    return v if isinstance(v, str) else None


@dataclasses.dataclass
class Record:
    name: str
    path: str
    manifest: dict = None
    state: str = "available"   # available | active | disabled | rejected
    generation: int = 0
    failures: int = 0
    reason: str = ""
    loaded_at: str = None
    inflight: int = 0
    instance: object = None
    contract: dict = None      # 그 kind 의 입출력 계약 표
    protocol: str = None       # inproc | process

    @property
    def kind(self):
        return (self.manifest or {}).get("kind")

    @property
    def runtime(self):
        return (self.manifest or {}).get("runtime", "inproc")


def contract_view(kind):
    """계약 표를 JSON 으로 보일 수 있게 타입 이름으로 바꾼다."""
    table = contract.EXTENSION_POINTS.get(kind) if isinstance(kind, str) else None
    table = table or {}
    return {op: {side: {f: t.__name__ for f, t in spec[side].items()} for side in ("in", "out")}
            for op, spec in table.items()}


class Registry:
    def __init__(self, state_path):
        self.lock = threading.Lock()
        self.records = {}
        self.state_path = state_path

    def load_states(self):
        """plugins.json 을 읽는다. 파일이 없으면 None."""
        if not os.path.exists(self.state_path):
            return None
        with open(self.state_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_states(self):
        """잠금을 잡은 쪽에서 부른다. 임시 파일에 쓰고 os.replace 로 바꾼다."""
        data = {n: {"state": r.state, "reason": r.reason}
                for n, r in sorted(self.records.items()) if r.state in ("active", "disabled")}
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.state_path)

    def view(self, rec):
        """MANIFEST 원시 값은 타입을 확인한 것만 낸다(rejected 기록의 값이 응답·UI 를 깨지 않게)."""
        m = rec.manifest if isinstance(rec.manifest, dict) else {}
        formats = m.get("formats")
        order = m.get("order")
        return {"name": rec.name, "kind": _str(m.get("kind")), "runtime": rec.runtime,
                "state": rec.state, "version": _str(m.get("version")), "description": _str(m.get("description")),
                "generation": rec.generation, "failures": rec.failures, "reason": rec.reason,
                "loaded_at": rec.loaded_at, "inflight": rec.inflight,
                "formats": formats if isinstance(formats, list) and all(isinstance(f, str) for f in formats) else None,
                "order": order if type(order) is int and -2**63 <= order < 2**63 else None,
                "contract": contract_view(m.get("kind"))}
