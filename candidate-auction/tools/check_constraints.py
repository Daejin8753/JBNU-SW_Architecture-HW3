"""kernel/constraints.py 를 plugins/ 전체(또는 인자로 준 폴더)에 돌린다.

실행: python tools/check_constraints.py [폴더]
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
    files = sorted(glob.glob(os.path.join(folder, "*.py")))
    bad = 0
    for path in files:
        found = constraints.check_file(path)
        name = os.path.basename(path)
        if found:
            bad += 1
            for line, msg in found:
                print(f"위반 {name}:{line} {msg}")
        else:
            print(f"통과 {name}")
    print(f"파일 {len(files)}개, 위반 파일 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
