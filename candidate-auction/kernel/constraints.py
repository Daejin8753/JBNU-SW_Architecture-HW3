"""정적 의존 검사. 적재·tools·시험이 같은 함수를 쓴다.

구조 제약 장치다. 보안 샌드박스가 아니다.
"""
import ast

# 플러그인이 import 해도 되는 모듈(허용 목록)
ALLOWED_IMPORTS = frozenset({
    "kernel.contract",
    "math", "re", "json", "time", "datetime", "decimal", "statistics",
    "string", "textwrap", "unicodedata", "html", "html.parser",
    "xml.etree.ElementTree", "csv", "io", "base64", "collections",
    "itertools", "functools", "dataclasses", "typing", "enum", "heapq",
    "bisect", "copy",
})

FORBIDDEN_NAMES = frozenset({"open", "__import__", "exec", "eval", "compile"})


def read_manifest_node(tree):
    """최상위 MANIFEST = {...} 를 실행 없이 읽는다. 없으면 None."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "MANIFEST":
                return ast.literal_eval(node.value)
    return None


def _allowed(name, extra):
    if name in ALLOWED_IMPORTS:
        return True
    return any(name == r or name.startswith(r + ".") for r in extra)


def check_source(source, filename="<plugin>"):
    """위반 목록 [(줄 번호, 문장)] 을 돌려준다. 빈 목록이면 통과."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return [(e.lineno or 0, f"구문 오류: {e.msg}")]
    extra = ()
    try:
        manifest = read_manifest_node(tree)
    except (ValueError, SyntaxError):
        manifest = None
    if isinstance(manifest, dict) and manifest.get("runtime") == "process":
        req = manifest.get("requires") or []
        if isinstance(req, list):
            extra = tuple(str(r) for r in req)

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _allowed(alias.name, extra):
                    found.append((node.lineno, f"허용되지 않은 import: {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.append((node.lineno, "상대 import 금지"))
                continue
            mod = node.module or ""
            if _allowed(mod, extra):
                continue
            for alias in node.names:
                if not _allowed(f"{mod}.{alias.name}", extra):
                    found.append((node.lineno, f"허용되지 않은 import: {mod}.{alias.name}"))
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            found.append((node.lineno, f"금지된 이름 사용: {node.id}"))
    found.sort()
    return found


def check_file(path):
    with open(path, encoding="utf-8") as f:
        return check_source(f.read(), str(path))


def format_violations(found):
    return "; ".join(f"{line}행 {msg}" for line, msg in found)
