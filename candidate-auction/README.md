# 온라인 경매 — 마이크로커널 아키텍처 (후보 A)

경매 절차를 가진 작은 코어에 경매 방식과 알림을 플러그인으로 꽂는 시스템이다. Python 3.14 표준 라이브러리만 쓴다.

## 실행

Windows 에서는 저장소 루트의 `run-auction.bat` 을 더블클릭하면 Python 준비, 지난 상태 지우기, 서버 실행, 브라우저 탭 두 개 열기를 한 번에 합니다. 저장소를 아직 받지 않았으면 루트 [`README.md`](../README.md) 의 "비교용 후보 A(온라인 경매)를 한 줄로 실행" 줄을 씁니다.

```text
python app.py                      # http://127.0.0.1:8801
python app.py --port 8801 --data data --plugins plugins
python -m unittest discover -s tests
python tools/check_constraints.py  # plugins/ 정적 의존 검사
python tools/bench.py              # inproc ↔ process 호출 비용
```

브라우저에서 `http://127.0.0.1:8801` 을 연다. 탭 여러 개를 열고 각 탭 위쪽에 다른 이름을 넣으면 사용자 여러 명이 된다. 첫 실행에는 `autoload: False` 가 아닌 플러그인을 모두 설치한다. 그 뒤로는 `data/plugins.json` 의 상태를 따른다.

## 구조

```text
app.py                  커널 생성 → 내부 서버 등록 → 플러그인 적재 → HTTP 서버
kernel/contract.py      계약: CONTRACT_VERSION, EXTENSION_POINTS, Plugin, Rejected, Busy
kernel/registry.py      레지스트리: 이름 → 기록(계약 표, 프로토콜, 상태), plugins.json
kernel/loader.py        plugins/ 검색, MANIFEST 정적 읽기, 정적 검사, 적재·해제
kernel/constraints.py   정적 의존 검사(ast)
kernel/kernel.py        대상 선택, 입출력 계약 검사, 내부 서버 중계, 장애 격리, SSE 이벤트
kernel/flow.py          경매 절차(생성 → 진행 → 마감 → 정산), 경매별 잠금
kernel/context.py       플러그인 창구 ctx (log, internal)
kernel/plugin_host.py   별도 프로세스 실행기
kernel/trace.py         요청별 경로(최근 200건)
internal/storage.py     sqlite3 auctions·bids·notifications
internal/clock.py       마감 예약(heapq + Condition.wait)
internal/audit.py       감사 로그 audit.log
plugins/                english, sealed_second, dutch, outbid_notifier(process),
                        broken_type(시연, 기본 미적재), future_contract(시연, 계약 2.0)
examples/lowest_unique.py  새 방식 예제(plugins/ 에 복사해 설치)
adapters/http_adapter.py   HTTP ↔ 코어, SSE
adapters/process_adapter.py 별도 프로세스 ↔ 코어
ui/                     index.html, app.js, style.css
tools/                  check_constraints.py, bench.py
tests/                  unittest, fixtures/(위반·장애 예제)
```

요청 흐름: 브라우저 → `http_adapter` → `flow`(코어 절차) → `kernel.call` → 레지스트리 조회 → 플러그인 → (ctx → kernel → 내부 서버). 내부 서버 호출은 모두 `kernel.internal` 을 지난다.

## 플러그인 만드는 법

파일 하나가 플러그인 하나다. 파일 이름 = `MANIFEST["name"]` (`^[a-z0-9_]{1,40}$`).

```python
from kernel import contract

MANIFEST = {
    "name": "my_type", "kind": "auction_type", "contract": "1.0",
    "version": "1.0.0", "description": "설명",
    # 선택: "runtime": "process", "timeout_sec": 3, "requires": [...], "autoload": False
}

class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        ...  # 규칙 위반은 raise contract.Rejected("사유")
```

확장점(`kernel/contract.py` 의 `EXTENSION_POINTS`):

| kind | op | in | out |
|---|---|---|---|
| auction_type | validate_bid | auction, bids, bid, now | amount:int |
| auction_type | view | auction, bids, now | price:int\|None, visible_bids:list, bid_count:int |
| auction_type | on_bid_accepted | auction, bids, bid | close_now:bool, outbid:str\|None |
| auction_type | settle | auction, bids | winner:str\|None, price:int\|None |
| notifier | on_outbid | auction_id, item, user, new_price | notifications:list |

- import 는 허용 목록만 된다(`kernel.contract`, 계산용 표준 모듈). `os`·`sqlite3`·`open`·다른 플러그인 import 등은 적재 전에 거부된다.
- 저장·마감·알림 전송은 코어가 한다. 플러그인은 계산만 한다. 코어 밖과 닿는 길은 `ctx.log(msg)` 하나다(감사 로그).
- `Rejected` 는 장애가 아니다(HTTP 400). 그 밖의 예외와 출력 계약 위반은 장애다. 연속 3회면 `disabled` 가 되고 [다시 켜기]로만 돌아온다.

## 5분 시연 절차

1. `python app.py` 를 실행하고 브라우저 탭 두 개를 연다. 탭 1 이름 `갑`, 탭 2 이름 `을`.
2. [플러그인 관리]: `future_contract` 는 `rejected`(계약 버전 불일치), `broken_type` 은 `available`, `outbid_notifier` 는 runtime `process` 로 보인다.
3. 탭 1에서 english 경매(시작가 10000, 60초)를 만든다. 탭 2에 바로 나타난다. 갑 10000 입찰 → 을 10100 입찰은 "10,500원 이상" 으로 거부 → 을 10500 입찰. 탭 1에 알림이 뜬다.
4. sealed_second 경매를 만들고 둘 다 입찰한다. 마감 전에는 입찰 수만 보인다. 마감되면 두 탭에 낙찰자와 두 번째 금액이 함께 뜬다.
5. dutch 경매를 만들고 [현재가 수락] → 바로 낙찰·마감.
6. `examples/lowest_unique.py` 를 `plugins/` 에 복사(저장소 루트의 `demo-add-auction-type.bat` 더블클릭) → [다시 검색] → `lowest_unique` [설치] → 경매 방식 목록에 나타난다. 재시작하지 않는다.
7. `broken_type` [설치] → 그 방식으로 20초 경매를 만들고 입찰 3번 → 3번 모두 장애 메시지, 상태 `disabled`. 다른 경매는 계속 된다. 마감 시각이 지나면 그 경매는 `settle_pending` → [다시 켜기] → `closed`(유찰).
8. 진행 중 경매가 있는 상태에서 `english` [제거] → 409 거부 문장.
9. 입찰 결과 옆 [경로 보기] → `http_adapter → kernel → internal:storage … → registry → plugin:english → (plugin → kernel → internal:audit) … → plugin:outbid_notifier` hop 목록과 ms.

시연이 끝나면 `plugins/lowest_unique.py` 를 지우고 [다시 검색]한다.

## 한계

- 정적 검사와 ctx 는 구조 제약 장치다. 보안 샌드박스가 아니다. 허용 모듈 안에서의 우회(`__builtins__` 접근 등)는 막지 못한다.
- inproc 플러그인의 무한 루프·메모리 고갈은 막지 못한다. 별도 프로세스 플러그인만 시간 제한(기본 3초, 최대 30초)으로 끊는다.
- 별도 프로세스 플러그인은 ctx 를 쓰지 않는다(ctx = None). 필요한 데이터는 코어가 payload 에 넣는다.
- 알림은 입찰 잠금 밖에서 부르지만 응답 전에 끝난다. 알림 플러그인이 멈추면 입찰 응답이 최대 잠금 대기 + 시간 제한 + 정리 2초(기본 8초) 늦어진다. 입찰 자체는 확정이고 `notify_error` 가 붙는다.
- dutch 현재가는 화면이 열린 시점의 값이다. 화면은 주기 조회를 하지 않으므로 [새로 보기]를 누르거나 이벤트가 올 때 바뀐다. 수락 때는 서버 시각의 현재가로 확정한다.
- 인증이 없다. 이름 입력만으로 사용자를 구분한다.
- trace 는 메모리에만 있고 재시작하면 사라진다.
- 시각은 서버 `time.time()` 이다. 시스템 시계를 바꾸면 마감 시각이 어긋난다.
