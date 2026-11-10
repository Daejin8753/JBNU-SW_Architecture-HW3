"""요청별 경로 기록. 최근 200건만 메모리에 둔다."""
import contextvars
import secrets
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager

_current = contextvars.ContextVar("trace", default=None)
_parent = contextvars.ContextVar("trace_parent", default=None)


class Trace:
    def __init__(self, label):
        self.id = secrets.token_hex(6)
        self.label = label
        self.started_at = time.time()
        self.hops = []
        self._lock = threading.Lock()

    def to_dict(self):
        with self._lock:
            hops = [dict(h) for h in self.hops]
        return {"trace_id": self.id, "label": self.label,
                "started_at": self.started_at, "hops": hops}


class Tracer:
    def __init__(self, keep=200):
        self.keep = keep
        self._traces = OrderedDict()
        self._lock = threading.Lock()

    @contextmanager
    def request(self, label):
        """새 trace 를 현재 문맥으로 둔다."""
        tr = Trace(label)
        with self._lock:
            self._traces[tr.id] = tr
            while len(self._traces) > self.keep:
                self._traces.popitem(last=False)
        t1 = _current.set(tr)
        t2 = _parent.set(None)
        try:
            yield tr
        finally:
            _parent.reset(t2)
            _current.reset(t1)

    def get(self, trace_id):
        with self._lock:
            tr = self._traces.get(trace_id)
        return tr.to_dict() if tr else None

    def recent(self, limit=50):
        with self._lock:
            items = list(self._traces.values())[-limit:]
        out = []
        for tr in reversed(items):
            d = tr.to_dict()
            out.append({"trace_id": d["trace_id"], "label": d["label"],
                        "started_at": d["started_at"], "hop_count": len(d["hops"]),
                        "ok": all(h["ok"] for h in d["hops"])})
        return out


@contextmanager
def hop(frm, to, op):
    """실제로 지난 hop 하나를 기록한다. trace 밖이면 아무것도 하지 않는다."""
    tr = _current.get()
    if tr is None:
        yield None
        return
    with tr._lock:
        seq = len(tr.hops) + 1
        rec = {"seq": seq, "parent": _parent.get(), "from": frm, "to": to,
               "op": op, "ok": None, "ms": None}
        tr.hops.append(rec)
    token = _parent.set(seq)
    start = time.perf_counter()
    ok = False
    try:
        yield rec
        ok = True
    finally:
        _parent.reset(token)
        with tr._lock:
            rec["ms"] = round((time.perf_counter() - start) * 1000, 3)
            if rec["ok"] is None:
                rec["ok"] = ok


def current_id():
    tr = _current.get()
    return tr.id if tr else None
