# 후보 B — 문서 → Markdown 변환기 (마이크로커널) — 9판

`공통.md` 를 먼저 따른다. 폴더 `candidate-docconv/`, 포트 8802. 업로드 본문 상한 20MB. 이 문서의 MB 는 1024×1024 바이트다.

## 사용자가 하는 일

- 파일을 화면에 끌어다 놓거나 고른다. 여러 개면 하나씩 차례로 보낸다. 1개당 최대 20MB.
- 변환된 Markdown 을 미리 보고 `.md` 로 내려받는다. 미리보기는 원문 텍스트로 충분하다.
- 후처리를 체크박스로 켜고 끈다(frontmatter 붙이기, 공백 정리).
- 변환 기록을 본다: 파일 이름, 판별 형식, 쓴 변환기, 소요 ms, 성공·실패 사유, 경고. 결과를 다시 내려받는다.

## 구성요소 배치

| 구성요소 | 파일 | 기능 |
|---|---|---|
| 코어 | `kernel/` | 변환 절차 순서(받기 → 안전 검사 → 형식 판별 → 변환기 선택 → 변환 → 후처리(켠 것만, order 순) → 저장 → 응답), 확장점 2개(`converter`, `postprocessor`), 장애 격리, 추적 |
| 내부 서버 | `internal/inspector.py` | 형식 판별과 안전 검사(아래 규칙) |
| 내부 서버 | `internal/storage.py` | `<data>/files/<id>.in`·`<id>.md` 저장, sqlite3 `<data>/history.db` 에 기록·로그. `ctx.log` 의 대상 |
| 외부 서버 | `plugins/txt_conv.py` | 텍스트. 인코딩은 utf-8(BOM 포함) → cp949 순서로 시도 |
| 외부 서버 | `plugins/html_conv.py` | `html.parser`. h1~h6, p, br, ul/ol/li, a, strong/em, table(간단 표), pre/code. script·style 은 버린다 |
| 외부 서버 | `plugins/docx_conv.py` | `xml.etree`. 코어가 준 `members["word/document.xml"]` 의 문단, 제목 스타일(Heading1~6 → `#`), 표(`w:tbl` → MD 표), 굵게. `zipfile` 을 직접 쓰지 않는다 |
| 외부 서버 | `plugins/hwpx_conv.py` | `xml.etree`. `members` 의 `Contents/section*.xml` 에서 `hp:p`/`hp:t` 텍스트, 표(`hp:tbl`)는 간단히 |
| 외부 서버 | `plugins/pdf_conv.py` | `runtime: "process"`, `requires: ["fitz"]`, `timeout_sec: 15`. PyMuPDF 로 쪽별 텍스트 추출, 쪽 구분선. PyMuPDF 가 없으면 자식 기동이 실패해 `rejected`("PyMuPDF 없음") |
| 외부 서버 | `plugins/frontmatter_post.py` | `postprocessor`, order 10. title(첫 제목 또는 파일 이름), source_file, converter, converted_at |
| 외부 서버 | `plugins/whitespace_post.py` | `postprocessor`, order 20. 빈 줄 연속 2개 이하, 줄 끝 공백 제거 |
| 시연용 | `plugins/future_contract.py` | `contract: "2.0"` → `rejected` 시연 |
| 예제 | `examples/csv_conv.py` | CSV → MD 표. MANIFEST `formats: ["csv"]`, `match: {"extensions": [".csv"], "text": true}`. 기본 코드(inspector)는 csv 를 모른다(E1) |
| 어댑터 | `adapters/http_adapter.py` | HTTP ↔ 코어 계약 |
| 어댑터 | `adapters/process_adapter.py` | PDF 변환기 프로세스 ↔ 코어 계약. 바이트의 전송 표현은 공통 "별도 프로세스" 의 프로토콜을 따른다 |

## 형식 판별 (`internal/inspector.py`)

위에서부터 처음 맞는 것을 쓴다.

1. `%PDF-` 로 시작 → pdf.
2. zip(`PK\x03\x04`) → 아래 "ZIP 안전 열기"를 먼저 통과해야 한다. `[Content_Types].xml` + `word/document.xml` → docx. `mimetype` 내용이 `application/hwp+zip` → hwpx. 그 밖의 zip → `Rejected`("지원하지 않는 형식").
3. 코어가 넘겨준 `active` 변환기들의 MANIFEST `match`: 확장자가 맞고(소문자로 바꿔 비교, 점 포함 `".csv"`), `text: true` 면 텍스트로 읽힐 때 → 그 변환기의 형식(`formats` 의 유일한 값). 확장자가 겹치는 `match` 는 설치 단계에서 막으므로 맞는 변환기는 많아야 하나다.
4. 앞 1KB 에 HTML 태그(`<!doctype html`, `<html`, `<body`, `<p`, `<h1`~`<h6` 등) → html.
5. utf-8 또는 cp949 로 읽히면 → txt.
6. 그 밖 → `Rejected`("지원하지 않는 형식").

판별된 형식을 맡는 `active` 변환기가 없으면 `Rejected`("이 형식의 변환기가 설치되어 있지 않음").

## ZIP 안전 열기 (inspector)

- 압축 방식은 stored·deflate 만 받는다. 그 밖(bzip2·lzma 등)은 거부한다. bzip2 는 64KB 씩 읽어도 한 번에 크게 풀려 메모리를 묶을 수 없다(Python 3.14 실측: 200MB 항목을 64KB 씩 읽는 동안 최고 437MiB, deflate 는 0.6MiB).
- 항목 수 ≤ 2000. 변환에 필요한 항목(`*.xml`, `mimetype`)만 64KB 단위로 읽으며 실제로 읽은 바이트를 센다. 항목당 20MB, 합계 50MB 를 넘으면 그 자리에서 멈추고 거부한다.
- `zipfile` 은 헤더의 선언 크기까지만 풀어 준다. 선언 크기를 작게 고친 파일은 잘린 XML 이 되어 변환기에서 손상된 문서로 거부된다.
- `zipfile` 이 내는 예외(손상, CRC 오류, 암호화)는 모두 거부한다.
- 디스크에 풀지 않는다. 결과 `members: {이름: bytes}` 를 코어가 변환기 payload 에 넣는다.
- XML 항목(`*.xml`)은 UTF-8 만 받는다. UTF-8 로 디코딩되지 않거나, NUL 문자가 있거나, XML 선언의 `encoding` 이 utf-8 이 아니면(대소문자 무시) 거부한다. UTF-16 같은 인코딩으로 아래 DOCTYPE 검사를 피하지 못하게 하려는 것이다.
- 그다음 `<!DOCTYPE` 이 든 XML 항목을 대소문자 무시로 찾아 거부한다(엔티티 확장 방지).
- 이 거부들은 모두 `Rejected` 다(변환기 장애가 아님).

## 파일 이름·저장

- `X-Filename` 은 한 번만 URL 디코딩한다. 경로 구분자(`/`, `\`)와 제어 문자를 빼고 마지막 부분만 남겨 표시 이름으로 쓴다. 표시·frontmatter·내려받기 이름에만 쓴다.
- 저장 파일 이름은 서버가 만든 ID(`secrets.token_hex(6)`)다. 내려받기 `GET /api/files/{id}.md` 는 `^[0-9a-f]{12}$` 만 받는다. `Content-Disposition` 은 `filename*=UTF-8''…` 로 쓴다.
- 결과 Markdown 의 크기는 UTF-8 로 인코딩한 바이트 수로 잰다. 상한은 20MB 다.
  - 변환기 결과가 상한을 넘으면 그 변환은 `Rejected`(400, "결과가 20MB 를 넘음")다. 변환기의 장애로 세지 않는다.
  - 후처리기마다 그 결과를 잰다. 넘으면 그 단계만 건너뛰고 직전 Markdown 을 유지하고, 경고(code `rejected`, "결과가 20MB 를 넘음")를 붙인다. 후처리기의 장애로 세지 않는다.
- 저장 단계에서 내부 서버가 실패하면(`OSError`, `sqlite3.Error`) 코어는 다음 순서로 처리한다. 응답은 `internal`(500)이다.
  1. 그 변환이 쓴 파일(`.in`·`.md`)을 파일마다 따로 지운다. 한 파일의 지우기가 실패해도 다음 파일과 다음 단계를 계속한다.
  2. 지우기 결과와 상관없이 기록에 실패(사유 "저장 실패")를 한 번 남기려 시도한다. 지우지 못한 파일이 있으면 사유에 "파일 정리 실패" 를 덧붙인다. 기록도 실패하면 그대로 둔다.

## 확장점 op

| 확장점 | op | in | out |
|---|---|---|---|
| `converter` | `convert` | filename(str), format(str), data(bytes), members(dict: ZIP 항목 이름 → bytes. ZIP 형식이 아니면 빈 dict) | `{"markdown": str, "meta": dict}` |
| `postprocessor` | `process` | markdown, meta(filename, format, converter) | `{"markdown": str}` |

- 변환기는 입력 때문에 생긴 오류를 `Rejected`("손상된 문서")로 바꾼다. 대상은 다음과 같다.
  - XML 파싱의 `xml.etree.ElementTree.ParseError`·`LookupError`·`ValueError`·`RecursionError`
  - 디코딩의 `UnicodeDecodeError`
  - CSV 파싱의 `csv.Error`(필드 크기 상한 초과 포함)
  - PyMuPDF 의 열기·쪽 읽기 오류(`RuntimeError`·`ValueError`. `FileDataError` 포함)
  - 그 밖의 예외는 장애다.
- 암호가 걸린 PDF(`doc.needs_pass`)는 `Rejected`("암호가 걸린 PDF")다. 연 PDF 문서는 `finally` 에서 닫는다.
- `html_conv` 는 태그 순서가 어긋나거나 닫히지 않은 HTML 에서도 예외를 내지 않는다. 열려 있지 않은 요소의 닫는 태그는 무시하고, 가능한 만큼 변환한다.
- 변환기 MANIFEST: `formats`(str 목록, 1개 이상), 선택 `match`(dict. `extensions` 는 `.` 으로 시작하는 str 목록, `text` 는 bool). `match` 가 있으면 `formats` 는 정확히 1개다(아니면 `rejected`).
- install 거부(409): 같은 형식을 맡는 `active` 변환기가 이미 있을 때, 또는 `match.extensions` 가 다른 `active` 변환기의 `match.extensions` 와 하나라도 겹칠 때(소문자로 비교). 이 검사는 생명주기 잠금 안에서 한다.
- 후처리기 MANIFEST: `order`(int, bool 은 안 된다).
- 이 키의 타입이 틀리면 그 플러그인만 `rejected` 다(공통 "계약").
- 대상 선택: 형식 → 그 형식을 맡는 `active` 변환기 하나.
- 선택 단계 = 후처리. 후처리기 호출이 실패하면(code 무엇이든) 코어는 그 단계를 건너뛰고 결과에 경고를 붙인다(공통 "코어가 하는 일" 5. `fault` 만 그 후처리기의 장애로 센다). 변환은 성공으로 저장한다.
- `X-Post` 에 있는 이름이 레지스트리에 없거나 kind 가 `postprocessor` 가 아니면 변환을 시작하기 전에 `Rejected`(400)다. 기록은 있지만 `active` 가 아니면 그 단계만 건너뛰고 경고(code `unavailable`)를 붙인다.
- ctx 허용 목록: `ctx.log` → `storage.log` 만.

## 제약을 보여 주는 지점

- 변환기는 후처리기를 부르지 않는다. 변환기는 다른 변환기도 모른다. 순서는 코어가 정한다.
- 후처리기는 어느 변환기가 만들었는지 meta 로만 안다.
- 변환기는 zip 을 직접 열지 않는다. 안전 검사를 거친 항목만 코어에게서 받는다.

## 시연 자료

- `tools/make_samples.py` 가 `samples/` 를 만든다: sample.txt, sample.html, sample.docx, sample.hwpx(최소 구조), sample.pdf(PyMuPDF 가 있을 때만), sample.csv, broken.pdf(`%PDF-` 뒤가 깨진 파일), zipbomb.docx(`word/document.xml` 의 실제 내용이 상한을 넘는 파일. 같은 바이트를 스트리밍으로 반복해 써서 압축 파일은 작다).
- 본문은 직접 쓴 문장만 쓴다. 외부 문서를 복사하지 않는다.

## 도메인 HTTP API

- `POST /api/convert`: 본문 = 파일 바이트. 헤더 `X-Filename`(URL 인코딩), `X-Post`(켠 후처리기 이름, 쉼표 구분). 반환 `{ok, id, filename, format, converter, markdown, warnings, ms, trace_id}`. multipart 를 쓰지 않는다(Python 3.14 에 `cgi` 가 없음).
- `GET /api/history`, `GET /api/files/{id}.md`(내려받기).
- SSE 를 쓰지 않는다. 화면은 변환 응답과 탭을 열 때의 조회로 갱신한다.

## 추가 시험

- 형식별 판별과 변환 결과(제목·표가 MD 로 나오는지).
- 새 형식: csv 예제를 설치하기 전에는 sample.csv 가 txt 로, 설치한 뒤에는 csv(MD 표)로 변환된다.
- 압축 폭탄(zipbomb.docx), bzip2 로 압축한 docx, 압축 데이터 바이트 하나를 바꾼 docx(CRC 오류), 선언 크기를 작게 고친 docx(잘린 XML), DOCTYPE 이 든 XML → 400, 변환기 실패 수는 그대로, 서버는 계속 동작.
- `Content-Length` 없음 → 411, 20MB 초과 → 413(본문을 읽기 전), 경로 조작 파일 이름(`../../x.txt`, `C:\x.txt`) → 저장은 ID, 표시 이름은 `x.txt`, 형식이 틀린 다운로드 ID → 404.
- broken.pdf → 400(손상된 문서), `pdf_conv` 실패 수 0, 서버는 계속 동작.
- PyMuPDF 가 없는 환경: PDF 정상 변환·broken.pdf·암호 PDF 시험은 사유를 남기고 건너뛴다. 대신 `pdf_conv` 가 `rejected`("PyMuPDF 없음")이고, PDF 입력이 400("이 형식의 변환기가 설치되어 있지 않음")인지 확인한다.
- 같은 형식 변환기 중복 install 거부. `match.extensions` 가 겹치는 변환기 install 거부. `match` 가 있는데 `formats` 가 2개인 변환기 → `rejected`.
- 후처리기 장애 → 변환 결과는 나오고 경고가 붙는다. 후처리기가 `Rejected` 를 내도 같다(실패 수는 그대로).
- 크기 경계: 상한보다 50바이트 작은 ASCII 한 줄 TXT 를 만든다. 시험은 먼저 frontmatter 없이 변환해 결과 크기가 상한 - 50 바이트 이상인지 단언한다(아니면 시험 실패). 그다음 frontmatter 를 켜고 변환 → 200, `frontmatter_post` 의 `rejected` 경고 1건, 결과는 변환기 결과 그대로, 실패 수 0.
- 인코딩: DOCTYPE 이 든 `word/document.xml` 을 UTF-16 으로 넣은 docx, XML 선언 `encoding` 이 utf-8 이 아닌 docx → 400, `docx_conv` 실패 수 0.
- 깊은 중첩: 요소를 1만 단계 중첩한 hwpx section → 장애가 아니다(400 또는 200), `hwpx_conv` 실패 수 0, `active`.
- 깨진 HTML: `<table><tr><td>a</td></table></tr>` 를 3회 → 매번 200, `html_conv` 실패 수 0, `active`.
- CSV 입력 오류(csv 예제를 설치한 뒤): 한 칸이 `csv.field_size_limit()` 보다 긴 CSV 를 3회 → 매번 400("손상된 문서"), `csv_conv` 실패 수 0, `active`.
- 암호가 걸린 PDF(시험이 PyMuPDF 로 만든다) → 400("암호가 걸린 PDF"), `pdf_conv` 실패 수 0.
- 저장 실패: 시험에서 storage 의 `.md` 쓰기가 `OSError` 를 내게 바꾼다 → 500 `internal`, 기록에 실패 1건, `files/` 에 남은 파일 없음, 다음 변환은 성공. 지우기까지 실패하게 바꾼 경우 → 500, 기록의 사유에 "파일 정리 실패".
