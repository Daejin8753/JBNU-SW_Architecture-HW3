"""plugins/ 검색, 정적 검사, MANIFEST 정적 읽기, 적재·해제."""
import ast
import importlib.util
import inspect
import os
import re

from kernel import constraints, contract

NAME_RE = re.compile(r"^[a-z0-9_]{1,40}$")
REQUIRED_KEYS = ("name", "kind", "contract", "version", "description")


class LoadError(Exception):
    """적재 거부. 그 플러그인만 rejected 가 된다."""


def scan(plugins_dir):
    """이름 → 파일 경로."""
    found = {}
    if not os.path.isdir(plugins_dir):
        return found
    for fn in sorted(os.listdir(plugins_dir)):
        if fn.endswith(".py") and NAME_RE.match(fn[:-3]):
            found[fn[:-3]] = os.path.join(plugins_dir, fn)
    return found


def read_manifest(path):
    """모듈을 실행하지 않고 MANIFEST 를 읽는다."""
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        manifest = constraints.read_manifest_node(tree)
    except (OSError, SyntaxError, ValueError) as e:
        raise LoadError(f"MANIFEST 를 읽을 수 없음: {e}")
    if not isinstance(manifest, dict):
        raise LoadError("MANIFEST 리터럴 dict 가 없음")
    return manifest


def check_manifest(name, m):
    for key in REQUIRED_KEYS:
        if key not in m:
            raise LoadError(f"MANIFEST 필수 키 없음: {key}")
    if m["name"] != name:
        raise LoadError(f"MANIFEST name({m['name']}) 이 파일 이름과 다름")
    if m["kind"] not in contract.EXTENSION_POINTS:
        raise LoadError(f"알 수 없는 확장점: {m['kind']}")
    major = str(m["contract"]).split(".")[0]
    if major != contract.CONTRACT_VERSION.split(".")[0]:
        raise LoadError(f"계약 버전 불일치: 플러그인 {m['contract']}, 코어 {contract.CONTRACT_VERSION}")
    runtime = m.get("runtime", "inproc")
    if runtime not in ("inproc", "process"):
        raise LoadError(f"알 수 없는 runtime: {runtime}")
    if runtime != "process" and ("requires" in m or "timeout_sec" in m):
        raise LoadError("requires·timeout_sec 는 runtime process 에서만 쓴다")


def static_check(path):
    found = constraints.check_file(path)
    if found:
        raise LoadError("정적 검사 위반: " + constraints.format_violations(found))


def load_inproc(path, name, generation):
    """모듈을 실행해 Plugin 인스턴스를 만든다. sys.modules 에 남기지 않는다."""
    spec = importlib.util.spec_from_file_location(f"plugin_{name}_{generation}", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        raise LoadError(f"적재 중 예외: {type(e).__name__}: {e}")
    cls = getattr(module, "Plugin", None)
    if not (inspect.isclass(cls) and issubclass(cls, contract.Plugin)):
        raise LoadError("contract.Plugin 을 상속한 Plugin 클래스가 없음")
    if inspect.isabstract(cls):
        raise LoadError("handle 이 구현되지 않음")
    try:
        return cls()
    except Exception as e:
        raise LoadError(f"생성 중 예외: {type(e).__name__}: {e}")


def load(path, name, manifest, generation, base_dir):
    """정적 검사 → MANIFEST 검사 → 적재. 실패는 LoadError."""
    static_check(path)
    check_manifest(name, manifest)
    if manifest.get("runtime", "inproc") == "process":
        from adapters.process_adapter import ProcessPlugin
        inst = ProcessPlugin(path, manifest, base_dir)
        try:
            inst.start()
        except Exception as e:
            inst.close()
            raise LoadError(f"별도 프로세스 준비 실패: {e}")
        return inst
    return load_inproc(path, name, generation)


def unload(instance):
    close = getattr(instance, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass
