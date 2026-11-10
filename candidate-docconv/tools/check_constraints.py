"""plugins/ 전체에 정적 의존 검사를 돌린다. 사용: python tools/check_constraints.py [폴더]

위반이 있으면 종료 코드 1.
"""
import glob
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from kernel import constraints  # noqa: E402


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "plugins")
    total = 0
    files = sorted(glob.glob(os.path.join(folder, "*.py")))
    for path in files:
        _, bad = constraints.check_file(path)
        for line, msg in bad:
            print(f"{os.path.basename(path)}:{line}: {msg}")
        total += len(bad)
    print(f"검사 파일 {len(files)}개, 위반 {total}건")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
