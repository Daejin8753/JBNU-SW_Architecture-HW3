"""인터랙션 비용 측정: 같은 fixture 파일을 inproc 과 process 로 적재해 같은 op 를 200회 부른다.

실행: python tools/bench.py [--n 200]
"""
import argparse
import os
import statistics
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from adapters.process_adapter import ProcessPlugin  # noqa: E402
from kernel import loader  # noqa: E402

FIXTURE = os.path.join(BASE, "tests", "fixtures", "hang_notifier.py")
SIZES = [("1KB", 1024), ("100KB", 100 * 1024), ("1MB", 1024 * 1024)]


def measure(plugin, size, n):
    payload = {"auction_id": "bench", "item": "x" * size, "user": "u", "new_price": 1}
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        out = plugin.handle("on_outbid", payload, None)
        times.append((time.perf_counter() - t0) * 1000)
        assert len(out["notifications"][0]["message"]) == size
    times.sort()
    return statistics.mean(times), times[int(len(times) * 0.95) - 1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=200)
    n = p.parse_args().n
    manifest = loader.read_manifest(FIXTURE)
    manifest["timeout_sec"] = 30  # 1MB 왕복이 시간 제한에 걸리지 않게

    t0 = time.perf_counter()
    inproc = loader.load_inproc(FIXTURE, "hang_notifier", 1)
    inproc_start = (time.perf_counter() - t0) * 1000

    starts = []
    for _ in range(5):
        proc = ProcessPlugin(FIXTURE, manifest, BASE)
        proc.start()
        starts.append(proc.last_startup_ms)
        proc.close()
    proc = ProcessPlugin(FIXTURE, manifest, BASE)
    proc.start()

    print(f"호출 횟수: {n}회/크기")
    print()
    print("| 항목 | inproc | process |")
    print("|---|---|---|")
    print(f"| 기동 시간(준비 응답까지, ms) | {inproc_start:.2f} | {statistics.mean(starts):.1f} (5회 평균) |")
    try:
        for label, size in SIZES:
            im, ip = measure(inproc, size, n)
            pm, pp = measure(proc, size, n)
            print(f"| {label} 평균 ms | {im:.4f} | {pm:.3f} |")
            print(f"| {label} p95 ms | {ip:.4f} | {pp:.3f} |")
    finally:
        proc.close()


if __name__ == "__main__":
    main()
