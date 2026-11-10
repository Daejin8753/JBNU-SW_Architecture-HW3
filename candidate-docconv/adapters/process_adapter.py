"""별도 프로세스 플러그인 ↔ 코어 계약. 코어에는 inproc 플러그인과 같은 handle 모양으로 보인다."""
import json
import queue
import subprocess
import sys
import threading
import time

from kernel import contract
from kernel.plugin_host import decode, encode


class ProcessFault(Exception):
    """시간 초과·자식 종료·잘못된 응답·재기동 실패. 장애로 센다."""


class StartError(Exception):
    """처음 기동 때 준비 실패(적재 거부 사유)."""


class ProcessAdapter:
    def __init__(self, path, manifest, cwd):
        self.path = path
        self.cwd = cwd
        self.timeout = min(float(manifest.get("timeout_sec", 3)), 30.0)
        self._lock = threading.Lock()   # 자식 잠금: 한 번에 한 요청
        self._state = threading.Lock()  # 상태 잠금: 자식 참조·닫힘 표시(짧게 잡음)
        self._child = None              # (Popen, 읽기 큐)
        self._closed = False
        self._waiting = False
        self._seq = 0
        self.started_ms = None  # 마지막 기동에서 준비 응답까지 걸린 ms

    # 시험용 읽기 전용 값 -------------------------------------------------
    @property
    def busy(self):
        """자식 잠금이 잡혀 있는가."""
        return self._lock.locked()

    @property
    def waiting(self):
        """요청 한 줄을 다 쓴 뒤 응답을 기다리는 중인가."""
        return self._waiting

    @property
    def pid(self):
        """지금 등록된 자식의 pid. 없으면 None."""
        with self._state:
            return self._child[0].pid if self._child else None

    # 기동·정리 -----------------------------------------------------------
    def start(self):
        """install 때 부른다. 준비 실패면 StartError."""
        with self._lock:
            try:
                self._spawn(time.monotonic() + self.timeout)
            except ProcessFault as e:
                raise StartError(str(e)) from None

    def _spawn(self, deadline):
        """자식을 띄워 준비 응답 전에 등록한다. 닫혀 있으면 등록하지 않고 바로 정리한다."""
        t0 = time.perf_counter()
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "kernel.plugin_host", self.path],
                cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL)
        except OSError as e:
            raise ProcessFault(f"재기동 실패: {e}") from None
        lines = queue.Queue()
        threading.Thread(target=self._reader, args=(proc.stdout, lines), daemon=True).start()
        child = (proc, lines)
        with self._state:
            closed = self._closed
            if not closed:
                self._child = child
        if closed:
            self._reap(proc)
            raise ProcessFault("어댑터가 닫힘")
        msg = self._read(child, deadline)
        if not msg.get("ready"):
            self._drop(child)
            raise ProcessFault(msg.get("error") or "준비 실패")
        self.started_ms = round((time.perf_counter() - t0) * 1000, 3)
        return child

    @staticmethod
    def _reader(stream, lines):
        try:
            for line in stream:
                lines.put(line)
        except (OSError, ValueError):
            pass
        lines.put(None)  # 끝 표시

    def _drop(self, child):
        """그 자식의 참조를 떼어 낸 뒤 정리한다. 이미 떼어졌으면(다른 쪽이 정리함) 하지 않는다."""
        with self._state:
            if self._child is not child:
                return
            self._child = None
        self._reap(child[0])

    @staticmethod
    def _reap(proc):
        try:
            proc.kill()
            proc.wait(2)
        except Exception:
            pass
        for s in (proc.stdin, proc.stdout):
            try:
                s.close()
            except Exception:
                pass

    def _read(self, child, deadline):
        remain = deadline - time.monotonic()
        if remain <= 0:
            self._drop(child)
            raise ProcessFault("시간 초과")
        try:
            line = child[1].get(timeout=remain)
        except queue.Empty:
            self._drop(child)
            raise ProcessFault("시간 초과") from None
        if line is None:
            self._drop(child)
            raise ProcessFault("자식 종료")
        try:
            return json.loads(line.decode("utf-8"))
        except ValueError:
            self._drop(child)
            raise ProcessFault("잘못된 JSON 응답") from None

    # 호출 ---------------------------------------------------------------
    def handle(self, op, payload, ctx):
        if not self._lock.acquire(timeout=self.timeout):
            raise contract.Busy("플러그인이 바쁨, 다시 시도")
        try:
            with self._state:
                closed, child = self._closed, self._child
            if closed:
                raise ProcessFault("어댑터가 닫힘")
            deadline = time.monotonic() + self.timeout  # 잠금을 얻은 뒤 새로 잰다
            if child is None or child[0].poll() is not None:
                if child is not None:
                    self._drop(child)
                child = self._spawn(deadline)
            self._seq += 1
            rid = self._seq
            line = json.dumps({"id": rid, "op": op, "payload": encode(payload)}) + "\n"
            try:
                child[0].stdin.write(line.encode("utf-8"))
                child[0].stdin.flush()
            except (OSError, ValueError):
                self._drop(child)
                raise ProcessFault("요청 쓰기 실패") from None
            self._waiting = True
            try:
                resp = self._read(child, deadline)
            finally:
                self._waiting = False
            if not isinstance(resp, dict) or resp.get("id") != rid:
                self._drop(child)
                raise ProcessFault("응답 id 불일치")
            if resp.get("ok"):
                return decode(resp.get("result"))
            if resp.get("rejected"):
                raise contract.Rejected(resp.get("reason", ""))
            raise ProcessFault(resp.get("error", "알 수 없는 오류"))
        finally:
            self._lock.release()

    def close(self):
        """자식 잠금을 기다리지 않는다. 닫힘 표시를 세우고 참조를 떼어 낸 뒤 잠금 밖에서 정리한다."""
        with self._state:
            self._closed = True
            child, self._child = self._child, None
        if child is not None:
            self._reap(child[0])
