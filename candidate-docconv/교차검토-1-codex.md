정적 검토 결과다. 시험·서버·스크립트는 실행하지 않았다. 경로는 `candidate-docconv/` 기준이며, 재현 절차는 코드에서 추적했다.

**HOLD**

1. **UTF-16 XML은 DOCTYPE 검사를 우회한다.**  
   근거: `internal/inspector.py:16`, `internal/inspector.py:63`, `plugins/docx_conv.py:79`.  
   재현: 내부 엔티티와 DOCTYPE이 있는 정상 DOCX XML을 UTF-16으로 저장 → 바이트 정규식은 놓치고 ElementTree는 파싱한다. “DOCTYPE 포함 XML 거부” 위반이다. XML 인코딩을 고려하거나 파서의 DTD 처리 지점에서 거부해야 한다.

2. **입력에서 유발되는 오류가 `fault`로 집계되어 변환기를 끈다.**  
   근거: `plugins/docx_conv.py:79`, `plugins/hwpx_conv.py:35`, `plugins/html_conv.py:128`, `plugins/pdf_conv.py:31`.  
   재현: XML의 알 수 없는 인코딩은 `LookupError`, 깊게 중첩한 HWPX는 `RecursionError`, HTML `<html><table><tr></table></tr>`는 `None.append` 오류를 낸다. 암호화 PDF도 열기 이후 쪽 접근 오류가 보호 범위 밖이다. 각각 반복하면 입력 거부 대신 장애 누적으로 `disabled`가 된다. 입력 검사와 알려진 파싱 오류 처리를 보강하고 PDF는 `finally`로 닫아야 한다.

3. **잘못된 MANIFEST 하나가 앱 시작 전체를 실패시킨다.**  
   근거: `kernel/constraints.py:34`, `kernel/loader.py:57`, `kernel/kernel.py:68`, `kernel/kernel.py:141`.  
   재현: process 플러그인의 `requires=None` → 시작 `rescan`에서 `TypeError`. 또는 `formats=1` → 형식 충돌 검사에서 `TypeError`. 해당 플러그인만 `rejected`가 되지 않는다. MANIFEST 필드 타입을 사용 전에 검사하고 적재 오류로 변환해야 한다.

4. **재검색이 진행 중 호출의 기록을 삭제하여 install 409를 우회한다.**  
   근거: `kernel/kernel.py:107`, `kernel/kernel.py:179`, `kernel/kernel.py:233`.  
   재현: T1이 참조와 `inflight=1` 확보 → T2가 remove → 파일을 치우고 rescan → 파일 복원·rescan·install. 새 Record의 `inflight=0` 때문에 이전 호출이 남아도 설치된다. 적재 중 `available` 기록 역시 삭제될 수 있다. 진행·적재·정리 중 기록은 삭제하지 말고 같은 이름의 생명주기를 동기화해야 한다.

5. **종료 뒤 이미 확보된 참조가 자식을 다시 띄울 수 있다.**  
   근거: `kernel/kernel.py:88`, `kernel/kernel.py:232`, `adapters/process_adapter.py:118`, `adapters/process_adapter.py:145`.  
   재현: T1이 인스턴스를 확보하고 호출 직전 대기 → T2가 shutdown으로 자식 종료·레지스트리 참조 제거 → T1 재개 → `_proc=None`을 보고 새 자식 기동. 새 자식은 레지스트리에서 추적되지 않는다. 커널 종료 상태와 어댑터의 영구 종료 상태를 두고 재기동을 막아야 한다.

6. **코어가 구체적인 어댑터에 의존한다.**  
   근거: `kernel/kernel.py:6`, `kernel/loader.py:88`.  
   코어가 어댑터의 `Busy`를 import하고 로더가 `ProcessAdapter`를 직접 생성한다. 의존 경로 자체가 요청된 계층 경계와 어긋난다. 공통 오류는 계약으로 옮기고, 프로세스 어댑터 생성 함수는 시작점에서 연결하는 방향이 맞다.

7. **`requires`로 명시적인 의존 금지를 해제할 수 있다.**  
   근거: `kernel/constraints.py:31`, `kernel/constraints.py:38`, `kernel/loader.py:55`.  
   재현: process MANIFEST에 `requires=["os"]` 또는 `["internal.storage"]`를 넣고 해당 모듈을 import → 정적 검사 통과. 외부 패키지 선언이 파일·내부 서버 직접 접근까지 허용한다. 금지된 표준 모듈과 프로젝트 내부 경로는 `requires`와 별도로 차단해야 한다.

8. **GET과 조기에 거부된 POST에는 요청 추적이 없다.**  
   근거: `adapters/http_adapter.py:100`, `adapters/http_adapter.py:139`, `adapters/http_adapter.py:143`, `구현보고.md:190`.  
   재현: 기록 조회 또는 출처·본문 길이 오류 요청 → 응답에 `trace_id`와 `X-Trace-Id`가 없다. POST만 추적한다는 자체 결정은 공통 지시의 “요청마다”와 다르다. 요청 진입점에서 추적을 생성하고 오류 응답까지 전달해야 한다.

9. **저장 실패는 실패 기록을 남기지 않고 부분 파일을 남길 수 있다.**  
   근거: `internal/storage.py:58`, `kernel/flow.py:60`, `kernel/flow.py:66`, `구현보고.md:189`.  
   재현: DB는 쓰기 가능하지만 파일 저장에서 `OSError` 발생 → `CallError` 전용 처리 밖으로 빠져 기록 없이 500. `.in` 저장 후 `.md` 저장이 실패하면 입력 파일도 남는다. 저장 실패 기록과 부분 파일 정리를 추가해야 한다.

**NIT**

- `tests/test_lifecycle.py:62`: E2는 고정 0.3초 대기로 호출 진입을 가정한다. `busy`·`inflight` 확인으로 동기화하면 시험이 안정적이다.
- `tests/test_lifecycle.py:190`: E5 설치 거부 시험은 검색 결과가 비면 단언 없이 통과한다. 예상 fixture 이름 집합과 실제 기록을 먼저 대조해야 한다.
- `README.md:106`: 선언 크기 위조가 항상 CRC 단계에서 거부된다는 설명은 과도하다. CRC까지 맞춘 경우에는 변환기의 잘린 XML 거부 경로로 간다.

**판단 필요**

없음.

HOLD 9 · NIT 3 · 판단 필요 0