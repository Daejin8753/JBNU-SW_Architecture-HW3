정적 검토 결과다. 아래 재현 순서는 코드에서 구성했으며 실행하지 않았다. 경로는 `candidate-auction/` 기준이다.

**HOLD 목록**

1. **rescan이 진행 중 호출의 기록을 삭제한다.**  
   근거: `kernel/kernel.py:161`, `kernel/kernel.py:330`.  
   재현: `slow` 호출 중 remove → 파일 삭제 → rescan. `inflight`가 남았는데 기록이 삭제되어 마지막 호출이 자식을 정리하지 못한다. 파일을 다시 추가·설치하면 옛 호출이 새 기록의 `inflight`를 감소시킬 수도 있다.  
   수정: 진행 중 호출이나 인스턴스가 있으면 기록을 유지하고, 호출 종료 처리는 확보했던 Record를 기준으로 한다.

2. **다시 켜기와 마감이 겹치면 재정산을 놓친다.**  
   근거: `kernel/flow.py:214`, `kernel/flow.py:224`.  
   재현: 마감 스레드가 disabled 방식의 정산 실패를 받고 저장 직전에 멈춤 → 다른 스레드가 install하고 pending 목록 조회 → 아직 DB에는 open이므로 건너뜀 → 마감 스레드가 pending 저장. 방식은 active인데 경매는 계속 pending이다.  
   수정: 재활성화와 pending 전이를 동기화하거나, pending 저장 후 활성화 여부를 재확인해 재정산을 예약한다.

3. **늦은 입찰 이벤트가 마감 화면을 진행 중으로 되돌린다.**  
   근거: `kernel/flow.py:171`, `kernel/flow.py:195`, `kernel/flow.py:218`, `ui/app.js:301`.  
   재현: 입찰 저장 후 알림 호출에서 지연 → 예약 마감이 closed 이벤트 전송 → 입찰 응답 뒤 오래된 open 스냅샷 전송. UI가 이를 그대로 덮어쓰며 자동 복구하지 않는다.  
   수정: 경매별 revision을 응답·SSE에 넣고 오래된 갱신을 무시한다.

4. **생성과 제거의 경합으로 사용 중인 방식이 제거된다.**  
   근거: `kernel/flow.py:130`, `kernel/flow.py:136`, `kernel/kernel.py:242`, `kernel/kernel.py:253`.  
   재현: 생성 스레드가 active 확인 → 제거 스레드가 사용 경매 없음 확인 → 생성 저장 → 제거 완료. open 경매가 available 방식을 참조해 입찰이 503이 된다. 구현보고의 인정된 한계지만 지시서 위반이다.  
   수정: 생성과 제거가 공유하는 별도 잠금으로 검사와 결정을 묶는다.

5. **종료 후 진행 중 호출이 자식을 다시 띄울 수 있다.**  
   근거: `kernel/kernel.py:276`, `kernel/kernel.py:342`, `adapters/process_adapter.py:116`, `adapters/process_adapter.py:126`.  
   재현: 호출이 인스턴스 참조를 확보하고 멈춤 → shutdown이 자식 종료·레지스트리 참조 제거 → 호출 재개 → 어댑터가 새 자식 생성. 이후 종료할 참조가 레지스트리에 없다.  
   수정: 커널과 어댑터에 종료 상태를 두고, 종료 후 호출·재기동을 막으며 진행 중 호출과 정리를 동기화한다.

6. **느린 SSE 구독자의 소켓과 스레드를 정리하지 못한다.**  
   근거: `kernel/kernel.py:54`, `adapters/http_adapter.py:248`, `adapters/http_adapter.py:266`.  
   재현: 구독자가 읽기를 멈춰 서버의 소켓 쓰기가 막힘 → 큐 초과 또는 종료 → 종료 표시만 큐에 넣음. 핸들러는 쓰기에서 막혀 표시를 읽지 못하고, 소켓도 직접 닫지 않는다.  
   수정: 구독 연결을 추적해 초과·종료 시 소켓을 shutdown하고, 쓰기 대기도 제한한다.

7. **응답 전송 실패가 확정된 변경의 SSE를 없앤다.**  
   근거: `adapters/http_adapter.py:178`, `kernel/flow.py:169`, `kernel/flow.py:193`.  
   재현: 입찰 저장 후 요청자가 연결을 끊어 `_send`에서 예외 발생 → `after()` 미실행 → 다른 탭에 입찰·알림 이벤트가 전달되지 않는다.  
   수정: 확정된 변경의 후속 이벤트는 응답 전송 실패에도 실행되도록 보장한다.

8. **requires로 계층 의존 금지를 해제할 수 있다.**  
   근거: `kernel/constraints.py:30`, `kernel/constraints.py:47`, `kernel/loader.py:42`.  
   재현: process 플러그인에 `requires: ["internal"]`과 `import internal.storage`를 선언하면 정적 검사를 통과한다. 내부 서버 직접 의존 금지가 깨진다.  
   수정: 내부 네임스페이스와 금지 표준 모듈은 requires로 허용하지 못하게 하고, requires 형식을 검사한다.

9. **허용되는 정수 입찰이 저장 단계에서 500을 낸다.**  
   근거: `kernel/flow.py:149`, `plugins/english.py:42`, `internal/storage.py:99`.  
   재현: english 첫 입찰에 `2**63` 크기의 정수를 제출하면 규칙·계약 검사는 통과하지만 SQLite 바인딩에서 OverflowError가 발생한다.  
   수정: 저장·화면에서 지원할 금액 범위를 정해 입력 단계에서 검사하거나 저장 표현을 확장한다.

10. **process 적재는 Plugin 상속 계약을 검사하지 않는다.**  
    근거: `kernel/loader.py:75`, `kernel/plugin_host.py:24`.  
    재현: process 플러그인에 `contract.Plugin`을 상속하지 않은 일반 `Plugin` 클래스를 두면 인스턴스 생성만으로 ready·active가 된다. inproc과 검증 수준이 다르다.  
    수정: 자식 실행기에도 상속·추상 메서드 검사를 적용한다.

**NIT 목록**

1. `tests/test_lifecycle.py:123`의 저장 없음 검사는 약하다. `tests/fixtures/bad_output.py:18`이 항상 빈 목록을 반환하므로, 실제 저장소의 입찰 수를 검사해야 한다.
2. `tests/test_lifecycle.py:78`은 인스턴스 참조 제거만 확인한다. 이전 자식의 실제 종료도 확인해야 누수를 잡는다.
3. `tests/test_flow.py:95`는 `codes`가 비어도 통과한다. 실패 응답 9개, 예상 밖 예외, 모든 스레드 종료를 함께 검사해야 한다.
4. E6은 알림 보존을, 비공개 HTTP 시험은 lowest_unique의 상세·SSE를 검사하지 않는다(`tests/test_lifecycle.py:140`, `tests/test_e7_http.py:166`).
5. `README.md:89`의 시연 정리에는 제거 단계가 빠졌다. active 파일을 삭제하고 rescan해도 적재된 인스턴스는 남는다.

**판단 필요 목록**

1. `kernel/flow.py:201`은 비공개 방식도 입찰 성공 응답의 `bid`에 입찰자·금액을 반환한다. `A-경매.md:88`의 “view 결과만 밖으로”에 본인 입찰 확인 응답을 예외로 둘지 명시해야 한다. 현재 비공개 시험은 이 응답을 검사하지 않는다.

HOLD 10 · NIT 5 · 판단 필요 1