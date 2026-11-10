"""요청별 경로 기록. 최근 200건만 메모리에 둔다."""
import collections
import contextlib
import secrets
import threading
import time


class Trace:
    """요청 하나의 hop 목록. 요청 스레드 하나만 쓴다."""

    def __init__(self, label):
        self.trace_id = secrets.token_hex(4)
        self.label = label
        self.at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.hops = []
        self.ok = None
        self._stack = []
        self._seq = 0
        self._t0 = time.perf_counter()
        self.ms = None

    @contextlib.contextmanager
    def hop(self, frm, to, op):
        self._seq += 1
        rec = {"seq": self._seq, "parent": self._stack[-1] if self._stack else None,
               "from": frm, "to": to, "op": op, "ok": None, "ms": None}
        self.hops.append(rec)
        self._stack.append(rec["seq"])
        t0 = time.perf_counter()
        try:
            yield rec
            if rec["ok"] is None:
                rec["ok"] = True
        except BaseException:
            rec["ok"] = False
            raise
        finally:
            rec["ms"] = round((time.perf_counter() - t0) * 1000, 3)
            self._stack.pop()

    def note(self, frm, to, op, ok):
        """시간을 재지 않는 hop 하나(코어에 닿기 전에 거부된 요청용)."""
        self._seq += 1
        self.hops.append({"seq": self._seq, "parent": self._stack[-1] if self._stack else None,
                          "from": frm, "to": to, "op": op, "ok": ok, "ms": 0.0})

    def finish(self, ok):
        self.ok = ok
        self.ms = round((time.perf_counter() - self._t0) * 1000, 3)

    def summary(self):
        return {"trace_id": self.trace_id, "label": self.label, "at": self.at,
                "ok": self.ok, "ms": self.ms, "hops": len(self.hops)}

    def to_dict(self):
        d = self.summary()
        d["hops"] = [dict(h) for h in self.hops]
        return d


class TraceStore:
    def __init__(self, size=200):
        self._items = collections.OrderedDict()
        self._size = size
        self._lock = threading.Lock()

    def add(self, trace):
        with self._lock:
            self._items[trace.trace_id] = trace
            while len(self._items) > self._size:
                self._items.popitem(last=False)

    def get(self, trace_id):
        with self._lock:
            t = self._items.get(trace_id)
        return t.to_dict() if t else None

    def recent(self, limit=50):
        with self._lock:
            items = list(self._items.values())[-limit:]
        return [t.summary() for t in reversed(items)]
