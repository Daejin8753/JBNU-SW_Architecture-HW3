"""시험용: requires 에 적은 외부 패키지 import 는 정적 검사 통과(없으면 준비 실패로 rejected)."""
from kernel import contract
import not_installed_pkg_xyz

MANIFEST = {
    "name": "ok_requires",
    "kind": "notifier",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "requires 허용 예제",
    "runtime": "process",
    "requires": ["not_installed_pkg_xyz"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"notifications": []}
