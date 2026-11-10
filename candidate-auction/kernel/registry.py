"""레지스트리: 플러그인 이름 → 기록(입출력 계약, 접근 프로토콜, 상태)."""
import json
import os
import threading
from dataclasses import dataclass


@dataclass
class Record:
    name: str
    path: str
    manifest: dict = None
    state: str = "available"   # available | active | disabled | rejected
    generation: int = 0
    failures: int = 0
    reason: str = ""
    loaded_at: float = None
    inflight: int = 0
    contract: dict = None      # 그 kind 의 입출력 계약 표
    protocol: str = None       # inproc | process
    instance: object = None
    installing: bool = False

    def to_dict(self, describe):
        m = self.manifest or {}
        return {
            "name": self.name, "kind": m.get("kind"),
            "runtime": m.get("runtime", "inproc") if m else None,
            "state": self.state, "version": m.get("version"),
            "description": m.get("description"), "generation": self.generation,
            "failures": self.failures, "reason": self.reason,
            "loaded_at": self.loaded_at, "inflight": self.inflight,
            "protocol": self.protocol,
            "contract": describe(self.contract) if self.contract else None,
        }


class Registry:
    def __init__(self, state_path):
        self.lock = threading.Lock()
        self.records = {}
        self.state_path = state_path

    def get(self, name):
        return self.records.get(name)

    def load_saved(self):
        """plugins.json 을 읽는다. 없으면 None."""
        if not os.path.exists(self.state_path):
            return None
        with open(self.state_path, encoding="utf-8") as f:
            return json.load(f)

    def save_locked(self):
        """잠금을 잡은 쪽만 부른다. 임시 파일에 쓰고 os.replace 로 바꾼다."""
        data = {r.name: {"state": r.state, "reason": r.reason}
                for r in self.records.values() if r.state in ("active", "disabled")}
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.state_path)
