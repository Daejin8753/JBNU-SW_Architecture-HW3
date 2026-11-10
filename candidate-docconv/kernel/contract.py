"""플러그인 계약. 플러그인이 import 할 수 있는 유일한 kernel 모듈."""
import abc
import math

CONTRACT_VERSION = "1.0"

# 확장점 → op → 입력·출력 필드 표. 코어가 호출 전후에 이 표로 검사한다.
# converter 의 members 는 zip 이 아니면 빈 dict 다.
EXTENSION_POINTS = {
    "converter": {
        "convert": {
            "in": {"filename": str, "format": str, "data": bytes, "members": dict},
            "out": {"markdown": str, "meta": dict},
        },
    },
    "postprocessor": {
        "process": {
            "in": {"markdown": str, "meta": dict},
            "out": {"markdown": str},
        },
    },
}


class Rejected(Exception):
    """입력·도메인 규칙 거부. 장애로 세지 않는다."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = str(reason)


class Busy(Exception):
    """별도 프로세스 어댑터가 잠금 대기를 넘겼을 때 낸다. 플러그인은 내지 않는다."""


INT_MIN, INT_MAX = -2**63, 2**63


def check_values(value, path="결과"):
    """값이 전송 가능한 타입으로만 되어 있는지 깊이 끝까지 본다. 위반이면 사유 문자열, 아니면 None."""
    try:
        if value is None or isinstance(value, (bool, str, bytes)):
            return None
        if isinstance(value, int):
            return None if INT_MIN <= value < INT_MAX else f"{path}: 범위 밖 int"
        if isinstance(value, float):
            return None if math.isfinite(value) else f"{path}: 유한하지 않은 float"
        if isinstance(value, list):
            for i, v in enumerate(value):
                bad = check_values(v, f"{path}[{i}]")
                if bad:
                    return bad
            return None
        if isinstance(value, dict):
            for k, v in value.items():
                if not isinstance(k, str):
                    return f"{path}: str 이 아닌 키 {type(k).__name__}"
                bad = check_values(v, f"{path}.{k}")
                if bad:
                    return bad
            return None
        return f"{path}: 쓸 수 없는 타입 {type(value).__name__}"
    except RecursionError:
        return f"{path}: 너무 깊음"


class Plugin(abc.ABC):
    """모든 플러그인의 부모. handle 하나만 구현한다."""

    @abc.abstractmethod
    def handle(self, op, payload, ctx):
        """op 를 처리하고 dict 를 돌려준다."""
