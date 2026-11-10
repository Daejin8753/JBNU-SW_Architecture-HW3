# 문서 → Markdown 변환기 (마이크로커널)

txt · html · docx · hwpx · pdf 문서를 Markdown 으로 바꾸는 로컬 웹 앱이다. 변환기와 후처리기는 플러그인이고, 코어는 절차 순서·계약 검사·장애 격리·추적만 맡는다.

## 실행 방법

Python 3.14, 표준 라이브러리만 쓴다. PDF 변환기만 PyMuPDF(`fitz`)를 쓴다. PyMuPDF 가 없으면 `pdf_conv` 만 `rejected` 가 되고 나머지는 동작한다.

발표·시연에는 저장소 루트의 `run.bat`(또는 루트 README 의 한 줄 명령)을 쓴다. 준비부터 서버 실행·브라우저 열기까지 한 번에 하고, 매번 처음 상태로 시작한다.

아래는 명령을 하나씩 쓸 때다. 한꺼번에 붙여 넣지 않는다. `python app.py` 는 그 창을 차지하므로 나머지는 다른 창에서 실행하고, `<폴더>` 는 직접 채운다.

```bash
python app.py                    # http://127.0.0.1:8802
python app.py --port 0 --data <폴더> --plugins <폴더>   # 시험용 인자
python tools/make_samples.py     # samples/ 에 시연 자료 생성
python -B -m unittest discover -s tests   # 56건(PyMuPDF 가 있으면 1건 건너뜀)
python tools/check_constraints.py   # plugins/ 정적 의존 검사(위반 0건이어야 함)
python tools/bench.py               # inproc ↔ process 호출 비용
```

서버는 127.0.0.1 에만 bind 한다. 끄려면 실행 창에서 Ctrl+C.

## 구조

```text
app.py              커널 생성 → 내부 서버 등록 → 플러그인 적재 → HTTP 서버 시작
kernel/contract.py  계약: CONTRACT_VERSION, EXTENSION_POINTS, Plugin, Rejected, Busy, check_values
kernel/registry.py  레지스트리: 이름 → 기록(계약, 프로토콜, 상태), plugins.json
kernel/loader.py    plugins/ 검색, 정적 검사, MANIFEST 검사, 적재·해제
kernel/constraints.py 정적 의존 검사(ast)
kernel/kernel.py    대상 선택, 입출력 계약 검사, 내부 서버 중계, 장애 격리, 생명주기
kernel/flow.py      변환 절차(받기 → 안전 검사 → 형식 판별 → 변환기 선택 → 변환 → 후처리 → 저장 → 응답)
kernel/context.py   플러그인 창구 ctx (ctx.log → storage.log 만 허용)
kernel/plugin_host.py 별도 프로세스 쪽 실행기
kernel/trace.py     요청별 경로(최근 200건)
internal/inspector.py 내부 서버: ZIP 안전 열기, 형식 판별
internal/storage.py   내부 서버: 파일 저장, sqlite3 기록·로그
plugins/            외부 서버(파일 1개 = 플러그인 1개)
adapters/http_adapter.py    HTTP ↔ 코어 계약
adapters/process_adapter.py 별도 프로세스 플러그인 ↔ 코어 계약(JSON 한 줄, 바이트는 base64)
examples/csv_conv.py  새 형식 예제(기본 코드는 csv 를 모름)
ui/                 정적 HTML/CSS/JS (CDN 없음)
tools/              check_constraints.py, bench.py, make_samples.py
tests/              unittest 56건, fixtures/(장애·위반·MANIFEST 타입 예제)
```

| 구성요소 | 위치 |
|---|---|
| 코어 | `kernel/` |
| 내부 서버 | `internal/inspector.py`, `internal/storage.py` |
| 외부 서버 | `plugins/*.py` |
| 어댑터 | `adapters/http_adapter.py`, `adapters/process_adapter.py` |

## 플러그인 만드는 법 (계약 1.0)

파일 하나에 최상위 `MANIFEST`(리터럴 dict)와 `class Plugin(contract.Plugin)` 을 둔다. 로더는 MANIFEST 를 `ast.literal_eval` 로 읽으므로 계산식·변수를 쓰지 않는다.

```python
from kernel import contract

MANIFEST = {
    "name": "md_conv",          # 파일 이름과 같게
    "kind": "converter",        # converter | postprocessor
    "contract": "1.0",          # major 가 코어와 같아야 적재
    "version": "1.0.0",
    "description": "설명",
    "formats": ["md"],          # converter: 맡는 형식
    "match": {"extensions": [".md"], "text": True},  # converter 선택: 새 형식 판별 규칙
    # "order": 30,              # postprocessor: 실행 순서
    # "runtime": "process", "requires": ["fitz"], "timeout_sec": 15,  # 별도 프로세스
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        text = payload["data"].decode("utf-8")
        ctx.log("읽음")         # 코어 → storage.log
        return {"markdown": text, "meta": {}}
```

| 확장점 | op | 입력 | 출력 |
|---|---|---|---|
| `converter` | `convert` | filename, format, data(bytes), members(dict, ZIP 이 아니면 빈 dict) | markdown(str), meta(dict) |
| `postprocessor` | `process` | markdown, meta(filename, format, converter) | markdown(str) |

- 손상된 입력은 `contract.Rejected("손상된 문서")` 를 낸다. 장애로 세지 않고 400 이 된다.
- 그 밖의 예외와 출력 계약 위반은 장애다. 연속 3회면 `disabled` 가 되고 [다시 켜기]로만 돌아온다.
- import 는 허용 목록(`kernel/constraints.py` 의 `ALLOWED_IMPORTS`)만 쓴다. `os`, `open`, `zipfile`, 다른 플러그인 등은 적재 전에 거부된다.
- 같은 형식을 맡거나 `match.extensions` 가 겹치는(소문자 비교) active 변환기가 있으면 install 이 409 다. `match` 가 있으면 `formats` 는 정확히 1개다.

## 5분 시연 절차

1. `python tools/make_samples.py` → `python app.py` → 브라우저에서 `http://127.0.0.1:8802`.
2. [변환] 탭: `samples/sample.docx`, `sample.html`, `sample.hwpx`, `sample.pdf` 를 한꺼번에 끌어다 놓는다. 하나씩 차례로 변환되고, 제목(`#`)과 표가 Markdown 으로 나온다. [.md 내려받기]로 받는다.
3. 후처리 체크박스 두 개를 켜고 `sample.txt` 를 다시 넣는다. 앞에 frontmatter 가 붙고 연속 빈 줄이 2개로 줄어든다.
4. `zipbomb.docx`, `broken.pdf` 를 넣는다. 둘 다 실패 사유가 문장으로 보이고, [플러그인 관리]에서 `docx_conv`·`pdf_conv` 의 연속 실패 수는 0 이다.
5. `sample.csv` 를 넣는다 → 형식 `txt`, 경고 칸에 "확장자 .csv 와 판별한 형식(txt)이 다름" 이 뜬다. `examples/csv_conv.py` 를 `plugins/` 에 복사(저장소 루트의 `demo-add-csv.bat` 더블클릭, 또는 다른 창에서 `Copy-Item examples\csv_conv.py plugins\`) → [플러그인 관리] [다시 검색] → `csv_conv` [설치] → `sample.csv` 를 다시 넣으면 형식 `csv`, Markdown 표가 나온다(재시작 없음).
6. [플러그인 관리]: `future_contract` 는 `rejected`(계약 버전 불일치) 사유가 보인다. `html_conv` [제거] → `sample.html` 변환이 "이 형식의 변환기가 설치되어 있지 않음" 으로 실패, 다른 형식은 정상 → [설치]로 되돌린다.
7. 결과 카드나 기록의 [경로 보기] → [요청 경로] 탭에서 `http_adapter → kernel → internal:inspector → registry → plugin:… → internal:storage` hop 과 ms 를 본다.

(시연 5 에서 복사한 `plugins/csv_conv.py` 는 시연 뒤 지운다. `run.bat` 은 다음 실행 때 이것과 `data/` 를 지운다.)

## 한계

- 정적 검사와 `ctx` 는 구조 제약 장치다. 보안 샌드박스가 아니다. 허용 모듈 안에서의 우회(예: `__builtins__` 접근)는 막지 못한다.
- 프로세스 안(inproc) 플러그인의 무한 루프·메모리 고갈은 막지 못한다. 시간 제한으로 끊는 것은 별도 프로세스 플러그인(`pdf_conv`)뿐이다.
- 별도 프로세스 플러그인은 `ctx` 를 쓰지 않는다. 필요한 데이터는 코어가 payload 에 넣는다.
- 별도 프로세스 호출은 자식 하나에 한 번에 한 요청이다. 앞 요청이 멈추면 뒤 요청은 최대 (시간 제한 × 2 + 2초) 뒤 성공하거나 `busy`(503)를 받는다.
- `zipfile` 은 헤더의 선언 크기까지만 풀어 준다. 선언 크기를 작게 고친 파일은 잘린 XML 이 되어 변환기에서 손상된 문서로 거부된다(400, 변환기 실패 수 0). CRC 를 고치지 않은 파일은 그보다 먼저 inspector 의 CRC 검사에서 거부된다.
- 변환 품질은 간단한 구조(제목·문단·목록·표·굵게)까지만 다룬다. 이미지, 각주, 병합 셀, 중첩 표는 옮기지 않는다.
- 요청 경로는 메모리에만 있어 재시작하면 사라진다. `/api/` 아래 모든 요청을 기록한다(trace 조회 제외). 코어에 닿기 전에 거부된 요청(403·411·413·404)은 adapter hop 하나만 남는다.
