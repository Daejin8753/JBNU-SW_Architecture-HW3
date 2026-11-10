"""코어 공통 장치: 대상 선택, 입출력 계약 검사, 내부 서버 호출 중계, 장애 격리, 추적."""
import copy
import json
import os
import queue
import threading
import time

from kernel import contract, loader
from kernel.context import Context
from kernel.registry import Record, Registry
from kernel.trace import hop

FAULT_LIMIT = 3

# 오류 code → HTTP 상태
STATUS = {"rejected": 400, "fault": 503, "busy": 503, "unavailable": 503,
          "conflict": 409, "not_found": 404}

# ctx.internal 허용 목록 (server, op)
CTX_ALLOWED = {("audit", "write")}


class CallError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class Events:
    """SSE 구독자 관리. 구독자마다 크기 100 큐, put_nowait 로만 넣는다."""

    CLOSE = object()

    def __init__(self):
        self._lock = threading.Lock()
        self._subs = set()

    def subscribe(self):
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            self._subs.discard(q)

    def count(self):
        with self._lock:
            return len(self._subs)

    def _drop(self, q):
        # 큐를 비우고 종료 표시를 넣어 구독 스레드를 깨운다
        with self._lock:
            self._subs.discard(q)
        try:
            while True:
                q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(self.CLOSE)
        except queue.Full:
            pass

    def publish(self, etype, data):
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait((etype, data))
            except queue.Full:
                self._drop(q)

    def close_all(self):
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            self._drop(q)


class Kernel:
    def __init__(self, data_dir, plugins_dir, base_dir):
        self.data_dir = data_dir
        self.plugins_dir = plugins_dir
        self.base_dir = base_dir
        self.registry = Registry(os.path.join(data_dir, "plugins.json"))
        self.events = Events()
        self.internals = {}
        self._remove_guards = []
        self._activate_hooks = []

    # ---- 내부 서버 중계 ----
    def register_internal(self, name, server):
        self.internals[name] = server

    def internal(self, server, op, **args):
        """코어 → 내부 서버. 내부 서버 호출은 반드시 여기를 지난다."""
        with hop("kernel", f"internal:{server}", op):
            if op.startswith("_"):
                raise PermissionError(op)
            return getattr(self.internals[server], op)(**args)

    def _ctx_call(self, plugin, server, op, args):
        with hop(f"plugin:{plugin}", "kernel", f"ctx {server}.{op}"):
            if (server, op) not in CTX_ALLOWED:
                raise PermissionError(f"ctx 허용 목록 밖: {server}.{op}")
            if server == "audit":
                args = dict(args, source=plugin)
            result = self.internal(server, op, **args)
            return json.loads(json.dumps(result))

    # ---- 도메인 절차가 거는 갈고리 ----
    def add_remove_guard(self, fn):
        self._remove_guards.append(fn)

    def add_activate_hook(self, fn):
        self._activate_hooks.append(fn)

    # ---- 조회 ----
    def list_plugins(self):
        with self.registry.lock:
            return [r.to_dict(contract.describe) for r in self.registry.records.values()]

    def plugin_info(self, name):
        with self.registry.lock:
            rec = self.registry.get(name)
            return rec.to_dict(contract.describe) if rec else None

    def active_names(self, kind):
        with self.registry.lock:
            return [r.name for r in self.registry.records.values()
                    if r.state == "active" and r.manifest.get("kind") == kind]

    def instance_of(self, name):
        """시험·bench 용 읽기."""
        with self.registry.lock:
            rec = self.registry.get(name)
            return rec.instance if rec else None

    # ---- 생명주기 ----
    def rescan(self):
        found = loader.scan(self.plugins_dir)
        manifests = {}
        for name, path in found.items():
            try:
                manifests[name] = loader.read_manifest(path)
            except loader.LoadError:
                manifests[name] = None
        with self.registry.lock:
            recs = self.registry.records
            for name, path in found.items():
                if name not in recs:
                    recs[name] = Record(name=name, path=path, manifest=manifests[name])
                elif recs[name].state in ("available", "rejected"):
                    recs[name].manifest = manifests[name] or recs[name].manifest
            for name in list(recs):
                r = recs[name]
                if name not in found and r.state in ("available", "rejected") and not r.installing:
                    del recs[name]
        self.events.publish("plugin_changed", {"name": None, "state": "rescan"})
        return self.list_plugins()

    def load_startup(self):
        """시작 적재. plugins.json 이 없으면 autoload 가 False 가 아닌 것을 모두 설치한다."""
        self.rescan()
        saved = self.registry.load_saved()
        if saved is None:
            with self.registry.lock:
                names = [r.name for r in self.registry.records.values()
                         if not r.manifest or r.manifest.get("autoload", True) is not False]
        else:
            names = []
            with self.registry.lock:
                for name, entry in saved.items():
                    rec = self.registry.get(name)
                    if rec is None:
                        continue
                    if entry.get("state") == "disabled":
                        rec.state = "disabled"
                        rec.reason = entry.get("reason", "")
                    elif entry.get("state") == "active":
                        names.append(name)
        for name in names:
            try:
                self.install(name)
            except CallError:
                pass

    def install(self, name):
        """설치 = 다시 켜기. 정적 검사 → MANIFEST 검사 → 적재 → active."""
        with hop("kernel", "registry", f"install {name}"):
            with self.registry.lock:
                rec = self.registry.get(name)
                if rec is None:
                    raise CallError("not_found", f"플러그인 없음: {name} (다시 검색 필요)")
                if rec.installing:
                    raise CallError("conflict", "설치가 진행 중")
                if rec.inflight:
                    raise CallError("conflict", "이전 호출이 끝나는 중")
                rec.installing = True
                rec.generation += 1
                gen = rec.generation
                old, rec.instance = rec.instance, None
                rec.state = "available"
            err, inst, manifest = None, None, None
            try:
                if old is not None:
                    loader.unload(old)
                manifest = loader.read_manifest(rec.path)
                inst = loader.load(rec.path, name, manifest, gen, self.base_dir)
            except loader.LoadError as e:
                err = str(e)
            except Exception as e:
                err = f"적재 실패: {type(e).__name__}: {e}"
            finally:
                with self.registry.lock:
                    rec.installing = False
                    if manifest is not None:
                        rec.manifest = manifest
                    if err is None and inst is not None:
                        rec.state, rec.failures, rec.reason = "active", 0, ""
                        rec.loaded_at = time.time()
                        rec.contract = contract.EXTENSION_POINTS[manifest["kind"]]
                        rec.protocol = manifest.get("runtime", "inproc")
                        rec.instance = inst
                    else:
                        rec.state, rec.reason, rec.instance = "rejected", err or "적재 실패", None
                    self.registry.save_locked()
        self.events.publish("plugin_changed", {"name": name, "state": rec.state})
        if err:
            raise CallError("rejected", err)
        for fn in self._activate_hooks:
            fn(name, manifest["kind"])
        return self.plugin_info(name)

    def remove(self, name):
        """새 호출을 막는다. 진행 중 호출은 잡은 참조로 끝까지 간다."""
        with hop("kernel", "registry", f"remove {name}"):
            for guard in self._remove_guards:
                reason = guard(name)
                if reason:
                    raise CallError("conflict", reason)
            inst = None
            with self.registry.lock:
                rec = self.registry.get(name)
                if rec is None:
                    raise CallError("not_found", f"플러그인 없음: {name}")
                if rec.installing:
                    raise CallError("conflict", "설치가 진행 중")
                rec.state, rec.reason = "available", ""
                if rec.inflight == 0:
                    inst, rec.instance = rec.instance, None
                self.registry.save_locked()
        if inst is not None:
            loader.unload(inst)
        self.events.publish("plugin_changed", {"name": name, "state": "available"})
        return self.plugin_info(name)

    # ---- 호출 ----
    def call(self, name, op, payload, kind=None):
        """이름 지정 호출: 상태 확인 → 입력 계약 검사 → 호출 → 출력 계약 검사 → 집계."""
        with hop("kernel", "registry", f"lookup {name}"):
            with self.registry.lock:
                rec = self.registry.get(name)
                if rec is None or rec.state != "active":
                    state = rec.state if rec else "없음"
                    raise CallError("unavailable", f"플러그인 {name} 사용 불가(상태: {state})")
                if kind and rec.manifest.get("kind") != kind:
                    raise CallError("unavailable", f"플러그인 {name} 은 {kind} 가 아님")
                spec = rec.contract.get(op)
                if spec is None:
                    raise CallError("rejected", f"확장점에 없는 op: {op}")
                inst, gen, protocol = rec.instance, rec.generation, rec.protocol
                rec.inflight += 1
        try:
            bad = contract.check_fields(payload, spec["in"])
            if bad:
                raise CallError("rejected", f"입력 계약 위반: {bad}")
            ctx = None
            if protocol == "inproc":
                payload = copy.deepcopy(payload)
                ctx = Context(lambda s, o, a: self._ctx_call(name, s, o, a))
            with hop("kernel", f"plugin:{name}", op):
                try:
                    out = inst.handle(op, payload, ctx)
                except contract.Rejected as e:
                    raise CallError("rejected", e.reason)
                except contract.Busy as e:
                    raise CallError("busy", str(e) or "플러그인이 바쁨, 다시 시도")
                except Exception as e:
                    msg = f"{type(e).__name__}: {e}"
                    self._fault(name, gen, msg)
                    raise CallError("fault", f"플러그인 {name} 장애: {msg}")
                bad = contract.check_fields(out, spec["out"])
                if bad:
                    msg = f"출력 계약 위반: {bad}"
                    self._fault(name, gen, msg)
                    raise CallError("fault", f"플러그인 {name} 장애: {msg}")
            self._success(name, gen)
            return out
        finally:
            self._release(name)

    def _success(self, name, gen):
        with self.registry.lock:
            rec = self.registry.get(name)
            if rec and rec.state == "active" and rec.generation == gen:
                rec.failures = 0
                rec.reason = ""

    def _fault(self, name, gen, msg):
        changed = False
        with self.registry.lock:
            rec = self.registry.get(name)
            if not (rec and rec.state == "active" and rec.generation == gen):
                return
            rec.failures += 1
            rec.reason = msg
            if rec.failures >= FAULT_LIMIT:
                rec.state = "disabled"
                rec.reason = f"연속 {FAULT_LIMIT}회 장애: {msg}"
                self.registry.save_locked()
                changed = True
        if changed:
            self.events.publish("plugin_changed", {"name": name, "state": "disabled"})

    def _release(self, name):
        inst = None
        with self.registry.lock:
            rec = self.registry.get(name)
            if rec is None:
                return
            rec.inflight -= 1
            if rec.inflight == 0 and rec.state == "available" and not rec.installing:
                inst, rec.instance = rec.instance, None
        if inst is not None:
            loader.unload(inst)

    def shutdown(self):
        self.events.close_all()
        with self.registry.lock:
            insts = [r.instance for r in self.registry.records.values() if r.instance]
            for r in self.registry.records.values():
                r.instance = None
        for inst in insts:
            loader.unload(inst)
