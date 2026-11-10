"""내부 서버: 감사 로그(한 줄 JSON). ctx.log 의 대상."""
import json
import threading
import time


class Audit:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()

    def write(self, msg, source="kernel", **fields):
        rec = {"at": time.time(), "source": source, "msg": msg}
        rec.update(fields)
        line = json.dumps(rec, ensure_ascii=False)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return {"ok": True}

    def tail(self, limit=20):
        try:
            with open(self.path, encoding="utf-8") as f:
                lines = f.readlines()[-limit:]
        except FileNotFoundError:
            return []
        return [json.loads(x) for x in lines]
