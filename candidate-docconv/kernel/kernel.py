"""코어 공통 장치: 대상 선택, 입출력 계약 검사, 내부 서버 호출 중계, 장애 격리, 추적, 생명주기."""
import os
import threading
import time

from kernel import contract, loader
from kernel.context import Context
from kernel.registry import Record, Registry
from kernel.trace import Trace, TraceStore

MAX_FAILURES = 3


class CallError(Exception):
    """호출 실패. code: rejected / fault / busy / unavailable / internal (+ 생명주기·HTTP 용)."""

    STATUS = {"rejected": 400, "forbidden": 403, "not_found": 404, "conflict": 409,
              "length_required": 411, "too_large": 413, "internal": 500,
              "fault": 503, "busy": 503, "unavailable": 503}

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def status(self):
        return self.STATUS.get(self.code, 500)


def check_fields(spec, value):
    """필수 필드 존재와 isinstance 만 본다. 문제가 없으면 None."""
    if not isinstance(value, dict):
        return "dict 가 아님"
    for field, typ in spec.items():
        if field not in value:
            return f"{field} 없음"
        if not isinstance(value[field], typ):
            return f"{field} 타입이 {typ.__name__} 가 아님"
    return None


class Kernel:
    def __init__(self, data_dir, plugins_dir, process_factory):
        self.data_dir = data_dir
        self.plugins_dir = plugins_dir
        self.process_factory = process_factory  # app 이 넘긴 별도 프로세스 어댑터 생성 함수
        self.registry = Registry(os.path.join(data_dir, "plugins.json"))
        self.internals = {}
        self.traces = TraceStore()
        self._life = threading.Lock()  # 생명주기 잠금: install·remove·rescan·shutdown
        self._closed = False           # 레지스트리 Lock 안에서만 바꾼다

    # 내부 서버 -----------------------------------------------------------
    def register_internal(self, name, server):
        self.internals[name] = server

    def call_internal(self, server, op, trace, **args):
        """내부 서버 호출은 반드시 여기를 지난다. 내부 서버 실패는 internal."""
        with trace.hop("kernel", f"internal:{server}", op):
            try:
                return getattr(self.internals[server], op)(**args)
            except contract.Rejected as e:
                raise CallError("rejected", e.reason) from None
            except CallError:
                raise
            except Exception as e:
                raise CallError("internal", f"{server}.{op} 실패: {type(e).__name__}: {e}") from None

    # 시작·종료 -----------------------------------------------------------
    def start(self):
        """plugins/ 검색 → plugins.json 의 active 만 적재. 파일이 없으면 전부 적재 시도."""
        self.rescan()
        states = self.registry.load_states()
        if states is None:
            states = {n: {"state": "active"} for n in self.registry.records}
        for name, st in states.items():
            rec = self.registry.records.get(name)
            if rec is None:
                continue
            if st.get("state") == "active":
                try:
                    self.install(name)
                except CallError:
                    pass  # 그 플러그인만 rejected, 나머지는 계속
            elif st.get("state") == "disabled":
                with self.registry.lock:
                    rec.state = "disabled"
                    rec.reason = st.get("reason", "")
        with self.registry.lock:
            self.registry.save_states()

    def shutdown(self):
        """닫힘 표시를 먼저 세우고(생명주기 잠금은 기다리지 않음), 그다음 잠금을 얻어 인스턴스를 정리한다."""
        with self.registry.lock:
            self._closed = True
        with self._life:
            with self.registry.lock:
                insts = [r.instance for r in self.registry.records.values() if r.instance]
                for r in self.registry.records.values():
                    r.instance = None
            for inst in insts:
                loader.unload(inst)

    def _check_open(self):
        """생명주기 잠금을 얻은 뒤 부른다. 닫혔으면 아무것도 바꾸지 않고 거부."""
        with self.registry.lock:
            if self._closed:
                raise CallError("unavailable", "커널이 닫힘")

    # 생명주기 ------------------------------------------------------------
    def rescan(self, trace=None):
        trace = trace or Trace("rescan")
        with self._life, trace.hop("kernel", "registry", "rescan"):
            self._check_open()
            found = loader.scan(self.plugins_dir)
            added, dropped = [], []
            with self.registry.lock:
                recs = self.registry.records
                for name, path in found.items():
                    if name not in recs:
                        recs[name] = Record(name=name, path=path)
                        added.append(name)
                for name in list(recs):
                    r = recs[name]
                    # 끝나지 않은 기록(진행 중 호출·정리할 인스턴스)은 남긴다
                    if (name not in found and r.state in ("available", "rejected")
                            and r.inflight == 0 and r.instance is None):
                        del recs[name]
                        dropped.append(name)
                todo = [r for r in recs.values() if r.state in ("available", "rejected") and r.name in found]
            for rec in todo:  # 표시용 MANIFEST 정적 읽기(실행하지 않음)
                try:
                    rec.manifest = loader.constraints.check_file(rec.path)[0]
                except Exception:
                    pass
            return {"added": added, "dropped": dropped}

    def install(self, name, trace=None):
        """설치 겸 다시 켜기."""
        trace = trace or Trace("install")
        with self._life, trace.hop("kernel", "registry", "install"):
            self._check_open()
            reg = self.registry
            with reg.lock:
                rec = reg.records.get(name)
                if rec is None:
                    raise CallError("not_found", f"플러그인 없음: {name}")
                if rec.inflight:
                    raise CallError("conflict", "이전 호출이 끝나는 중")
                old, rec.instance = rec.instance, None
                rec.state = "available"  # 적재 중 새 호출을 막는다
            if old is not None:
                loader.unload(old)
            manifest = None
            try:
                manifest = loader.static_check(rec.path)
                loader.validate_manifest(manifest, name)
                if manifest["kind"] == "converter":
                    self._check_converter_conflict(name, manifest)
                gen = rec.generation + 1
                inst = loader.load(rec.path, name, manifest, gen, self.process_factory)
            except CallError as e:
                with reg.lock:
                    rec.manifest, rec.reason = manifest, e.message
                    reg.save_states()
                raise
            except Exception as e:  # LoadError 와 그 밖의 적재 예외는 그 플러그인만 rejected
                msg = str(e) if isinstance(e, loader.LoadError) else f"적재 중 예외: {type(e).__name__}: {e}"
                with reg.lock:
                    rec.manifest = manifest if isinstance(manifest, dict) else rec.manifest
                    rec.state, rec.reason = "rejected", msg
                    reg.save_states()
                raise CallError("rejected", msg) from None
            with reg.lock:
                rec.manifest = manifest
                rec.instance = inst
                rec.state, rec.reason, rec.failures = "active", "", 0
                rec.generation = gen
                rec.loaded_at = time.strftime("%Y-%m-%d %H:%M:%S")
                rec.contract = contract.EXTENSION_POINTS[manifest["kind"]]
                rec.protocol = manifest.get("runtime", "inproc")
                reg.save_states()
                return reg.view(rec)

    def _check_converter_conflict(self, name, manifest):
        """같은 형식, 또는 match.extensions 가 겹치는 active 변환기가 있으면 409(소문자 비교)."""
        mine = set(manifest["formats"])
        my_ext = {e.lower() for e in (manifest.get("match") or {}).get("extensions", [])}
        with self.registry.lock:
            for r in self.registry.records.values():
                if r.name == name or r.state != "active" or r.kind != "converter":
                    continue
                both = mine & set(r.manifest.get("formats", []))
                if both:
                    raise CallError("conflict", f"같은 형식({', '.join(sorted(both))})의 active 변환기가 이미 있음: {r.name}")
                ext = my_ext & {e.lower() for e in (r.manifest.get("match") or {}).get("extensions", [])}
                if ext:
                    raise CallError("conflict", f"확장자({', '.join(sorted(ext))})가 active 변환기와 겹침: {r.name}")

    def remove(self, name, trace=None):
        trace = trace or Trace("remove")
        with self._life, trace.hop("kernel", "registry", "remove"):
            self._check_open()
            with self.registry.lock:
                rec = self.registry.records.get(name)
                if rec is None:
                    raise CallError("not_found", f"플러그인 없음: {name}")
                rec.state, rec.reason = "available", ""
                inst = None
                if rec.inflight == 0:  # 진행 중 호출이 있으면 마지막 호출이 끝날 때 정리
                    inst, rec.instance = rec.instance, None
                self.registry.save_states()
                view = self.registry.view(rec)
            if inst is not None:
                loader.unload(inst)
            return view

    def list_plugins(self, trace=None):
        trace = trace or Trace("list")
        with trace.hop("kernel", "registry", "list"):
            with self.registry.lock:
                return [self.registry.view(r) for _, r in sorted(self.registry.records.items())]

    def plugin_info(self, name):
        with self.registry.lock:
            rec = self.registry.records.get(name)
            return self.registry.view(rec) if rec else None

    def instance_of(self, name):
        """시험·bench 용: 현재 인스턴스(별도 프로세스면 어댑터)."""
        with self.registry.lock:
            rec = self.registry.records.get(name)
            return rec.instance if rec else None

    # 대상 선택 -----------------------------------------------------------
    def converter_matchers(self):
        """active 변환기의 MANIFEST match 목록(inspector 에 넘긴다)."""
        with self.registry.lock:
            return [{"name": r.name, "formats": list(r.manifest["formats"]), "match": dict(r.manifest["match"])}
                    for _, r in sorted(self.registry.records.items())
                    if r.state == "active" and r.kind == "converter" and r.manifest.get("match")]

    def select_converter(self, fmt):
        """형식 → 그 형식을 맡는 active 변환기 하나."""
        with self.registry.lock:
            for _, r in sorted(self.registry.records.items()):
                if r.state == "active" and r.kind == "converter" and fmt in r.manifest.get("formats", []):
                    return r.name
        raise CallError("rejected", "이 형식의 변환기가 설치되어 있지 않음")

    # 호출 ----------------------------------------------------------------
    def call(self, name, op, payload, trace=None):
        """이름 지정 호출: 상태 확인 → 입력 계약 검사 → 호출 → 출력 계약 검사 → 집계."""
        trace = trace or Trace("direct")
        with trace.hop("kernel", "registry", "lookup"):
            with self.registry.lock:
                if self._closed:
                    raise CallError("unavailable", "커널이 닫힘")
                rec = self.registry.records.get(name)
                if rec is None or rec.state != "active":
                    raise CallError("unavailable", f"{name} 플러그인이 active 가 아님")
                spec = rec.contract.get(op)
                if spec is None:
                    raise CallError("rejected", f"{rec.kind} 에 없는 op: {op}")
                inst = rec.instance
                rec.inflight += 1
        outcome, message = "fault", ""
        try:
            bad = check_fields(spec["in"], payload)
            if bad:
                outcome = "rejected"
                raise CallError("rejected", f"입력 계약 위반: {bad}")
            try:
                with trace.hop("kernel", f"plugin:{name}", op):
                    out = inst.handle(op, payload, Context(self, name, trace))
            except contract.Rejected as e:
                outcome = "rejected"
                raise CallError("rejected", e.reason) from None
            except contract.Busy as e:
                outcome = "busy"
                raise CallError("busy", str(e) or "플러그인이 바쁨, 다시 시도") from None
            except CallError as e:  # ctx 로 부른 내부 서버의 실패: 플러그인 장애가 아니다
                outcome = e.code
                raise
            except Exception as e:
                message = f"{type(e).__name__}: {e}"
                raise CallError("fault", f"{name} 장애: {message}") from None
            bad = check_fields(spec["out"], out) or contract.check_values(out)
            if bad:
                message = f"출력 계약 위반: {bad}"
                raise CallError("fault", f"{name} {message}")
            outcome = "ok"
            return out
        except CallError as e:
            with self.registry.lock:
                closed = self._closed
            if closed:  # 종료 중의 실패는 unavailable
                raise CallError("unavailable", f"커널이 닫힘: {e.message}") from None
            raise
        finally:
            self._finish(rec, outcome, message)

    def _finish(self, rec, outcome, message):
        inst = None
        with self.registry.lock:
            rec.inflight -= 1
            if rec.state == "active" and not self._closed:  # 닫힌 뒤에는 집계하지 않는다
                if outcome == "ok":
                    rec.failures = 0
                elif outcome == "fault":
                    rec.failures += 1
                    if rec.failures >= MAX_FAILURES:
                        rec.state = "disabled"
                        rec.reason = f"연속 {rec.failures}회 장애: {message}"
                        self.registry.save_states()
            if rec.state != "active" and rec.inflight == 0 and rec.instance is not None:
                inst, rec.instance = rec.instance, None
        if inst is not None:
            loader.unload(inst)
