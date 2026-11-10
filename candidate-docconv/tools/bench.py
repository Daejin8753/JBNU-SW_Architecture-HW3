"""인터랙션 비용 측정. 같은 fixture 파일(tests/fixtures/hang_conv.py)을 inproc·process 로 적재해
convert 를 크기별 200회 호출한다. 사용: python tools/bench.py [횟수]
"""
import os
import statistics
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from adapters.process_adapter import ProcessAdapter  # noqa: E402
from kernel import constraints, loader  # noqa: E402

FIXTURE = os.path.join(BASE, "tests", "fixtures", "hang_conv.py")
SIZES = [("1KB", 1024), ("100KB", 100 * 1024), ("1MB", 1024 * 1024)]


def measure(plugin, size, n):
    payload = {"filename": "bench", "format": "hangfmt", "data": b"a" * size, "members": {}}
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        out = plugin.handle("convert", payload, None)
        times.append((time.perf_counter() - t0) * 1000)
        assert out["markdown"] == f"bench:{size}"
    times.sort()
    return statistics.mean(times), times[int(len(times) * 0.95) - 1]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    manifest, _ = constraints.check_file(FIXTURE)

    t0 = time.perf_counter()
    inproc = loader.load_inproc(FIXTURE, "hang_conv", 1)
    inproc_start = (time.perf_counter() - t0) * 1000

    adapter = ProcessAdapter(FIXTURE, manifest, BASE)
    adapter.start()
    try:
        rows = []
        for label, size in SIZES:
            a = measure(inproc, size, n)
            b = measure(adapter, size, n)
            rows.append((label, a, b))
    finally:
        adapter.close()

    print(f"호출 횟수: 크기별 {n}회, fixture: tests/fixtures/hang_conv.py")
    print()
    print("| 항목 | inproc | process |")
    print("|---|---|---|")
    print(f"| 기동(준비 응답까지) ms | {inproc_start:.2f} (모듈 실행) | {adapter.started_ms:.2f} |")
    for label, a, b in rows:
        print(f"| {label} 평균 ms | {a[0]:.4f} | {b[0]:.3f} |")
        print(f"| {label} p95 ms | {a[1]:.4f} | {b[1]:.3f} |")


if __name__ == "__main__":
    main()
