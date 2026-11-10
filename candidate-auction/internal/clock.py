"""내부 서버: 마감 예약.

heapq + Condition.wait(timeout) 로 다음 마감 시각까지 잠든다. 주기 폴링을 하지 않는다.
"""
import heapq
import threading
import time


class Clock:
    def __init__(self, on_due, on_error=None):
        self._on_due = on_due          # 코어의 마감 절차
        self._on_error = on_error
        self._heap = []
        self._cond = threading.Condition()
        self._stopped = False
        self._thread = None
        self.last_wait_timeout = "not_started"  # 시험용: 마지막 wait 의 timeout(None = 무기한)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="auction-clock", daemon=True)
        self._thread.start()

    def schedule(self, auction_id, ends_at):
        with self._cond:
            earliest = not self._heap or ends_at < self._heap[0][0]
            heapq.heappush(self._heap, (ends_at, auction_id))
            if earliest:
                self._cond.notify()

    def pending(self):
        with self._cond:
            return len(self._heap)

    def stop(self):
        with self._cond:
            self._stopped = True
            self._cond.notify()
        if self._thread:
            self._thread.join(2)

    def _run(self):
        while True:
            with self._cond:
                while True:
                    if self._stopped:
                        return
                    if not self._heap:
                        self.last_wait_timeout = None
                        self._cond.wait()          # 예약이 없으면 timeout 없이
                        continue
                    ends_at, auction_id = self._heap[0]
                    delay = ends_at - time.time()
                    if delay > 0:
                        self.last_wait_timeout = delay
                        self._cond.wait(delay)
                        continue
                    heapq.heappop(self._heap)
                    break
            try:
                self._on_due(auction_id)
            except Exception as e:  # 기록하고 다음 예약을 계속한다
                if self._on_error:
                    try:
                        self._on_error(auction_id, e)
                    except Exception:
                        pass
