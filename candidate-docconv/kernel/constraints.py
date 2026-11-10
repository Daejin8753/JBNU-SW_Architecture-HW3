"""플러그인 파일 정적 의존 검사. 모듈을 실행하지 않는다."""
import ast
import sys

# 플러그인이 import 할 수 있는 모듈(허용 목록)
ALLOWED_IMPORTS = frozenset({
    "kernel.contract",
    "math", "re", "json", "time", "datetime", "decimal", "statistics",
    "string", "textwrap", "unicodedata", "html", "html.parser",
    "xml.etree.ElementTree", "csv", "io", "base64", "collections",
    "itertools", "functools", "dataclasses", "typing", "enum", "heapq",
    "bisect", "copy",
})

BANNED_NAMES = frozenset({"open", "__import__", "exec", "eval", "compile"})

# requires 에 적을 수 없는 최상위 이름: 후보 폴더의 패키지·모듈
LOCAL_PACKAGES = frozenset({"kernel", "internal", "adapters", "plugins", "tools", "tests", "examples", "app"})


def requires_problem(name):
    """requires 항목 하나가 외부 패키지가 아니면 사유, 맞으면 None."""
    if not isinstance(name, str) or not name:
        return "requires 항목이 str 이 아님"
    top = name.split(".")[0]
    if top in sys.stdlib_module_names:
        return f"requires 에 표준 모듈: {name}"
    if top in LOCAL_PACKAGES:
        return f"requires 에 후보 폴더 패키지: {name}"
    return None


def read_manifest(tree):
    """최상위 MANIFEST = {...} 를 literal_eval 로 읽는다. 없거나 리터럴이 아니면 None."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if isinstance(t, ast.Name) and t.id == "MANIFEST":
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                    return None
                return value if isinstance(value, dict) else None
    return None


def _requires(manifest):
    """process 이고 목록인 requires 만 돌려준다(타입 위반은 loader 의 MANIFEST 검사가 잡는다)."""
    if not manifest or manifest.get("runtime") != "process":
        return []
    req = manifest.get("requires", [])
    return req if isinstance(req, list) else []


def _allowed(manifest):
    allowed = set(ALLOWED_IMPORTS)
    allowed.update(x for x in _requires(manifest) if requires_problem(x) is None)
    return allowed


def _module_ok(name, allowed):
    # 외부 패키지는 하위 모듈도 허용한다(예: fitz.utils)
    if name in allowed:
        return True
    return any(name.startswith(a + ".") for a in allowed if a not in ALLOWED_IMPORTS)


def check_source(source, filename="<plugin>"):
    """(manifest, [(줄 번호, 사유)]) 를 돌려준다."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return None, [(e.lineno or 1, f"구문 오류: {e.msg}")]
    except (ValueError, MemoryError, RecursionError) as e:  # NUL 문자, 너무 깊은 식 등
        return None, [(1, f"구문 오류: {type(e).__name__}")]
    manifest = read_manifest(tree)
    allowed = _allowed(manifest)
    bad = []
    for x in _requires(manifest):
        problem = requires_problem(x)
        if problem:
            bad.append((1, problem))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if not _module_ok(a.name, allowed):
                    bad.append((node.lineno, f"허용되지 않은 import: {a.name}"))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                bad.append((node.lineno, "상대 import 금지"))
                continue
            mod = node.module or ""
            for a in node.names:
                if not (_module_ok(mod, allowed) or _module_ok(f"{mod}.{a.name}", allowed)):
                    bad.append((node.lineno, f"허용되지 않은 import: from {mod} import {a.name}"))
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            bad.append((node.lineno, f"금지된 이름 사용: {node.id}"))
    bad.sort()
    return manifest, bad


def check_file(path):
    """읽기 실패(UTF-8 아님 등)도 위반 1건으로 돌려준다."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError) as e:
        return None, [(1, f"파일 읽기 실패: {type(e).__name__}")]
    return check_source(source, path)
