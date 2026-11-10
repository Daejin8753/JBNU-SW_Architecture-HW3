# 후보 A — 온라인 경매 (마이크로커널) — 6판

`공통.md` 를 먼저 따른다. 폴더 `candidate-auction/`, 포트 8801.

## 사용자가 하는 일

- 화면 위쪽에 내 이름을 입력한다(인증 없음). 브라우저 탭 여러 개 = 사용자 여러 명.
- 경매 만들기: 물품명, 시작가(1~100,000,000 원, 정수), 진행 시간(1~3600초), 경매 방식. 경매 방식은 `active` 인 `auction_type` 플러그인 목록에서 고른다.
- 경매 목록·상세: 상태, 현재가, 남은 시간, 공개된 입찰 기록.
- 입찰한다. 거부되면 사유가 보인다. dutch 는 금액 입력 없이 [현재가 수락]이다.
- 마감되면 낙찰자·낙찰가(또는 유찰)가 모든 탭에 바로 보인다(SSE).
- 내가 최고 입찰에서 밀리면 알림이 뜬다.

## 구성요소 배치

| 구성요소 | 파일 | 기능 |
|---|---|---|
| 코어 | `kernel/` | 경매 절차(생성 → 진행 → 마감 → 정산) 순서와 상태 전이, 경매별 잠금, 확장점 2개(`auction_type`, `notifier`), 장애 격리, 추적 |
| 내부 서버 | `internal/storage.py` | sqlite3 `<data>/auction.db`: auctions, bids, notifications 표. 새 입찰 저장과 경매 상태 변경을 트랜잭션 하나로 하는 함수를 둔다 |
| 내부 서버 | `internal/clock.py` | 마감 예약. `heapq` + `threading.Condition.wait(timeout)` 로 다음 마감 시각까지 잠든다. 예약이 없으면 timeout 없이 기다린다. 주기 폴링 금지. 더 이른 경매가 생기면 `notify` 로 깨운다. 마감 시각이 되면 코어의 마감 절차를 부르고, 예외는 잡아 기록한 뒤 다음 예약을 계속한다. 시작 때 `open` 경매를 다시 예약하고 이미 지난 것은 바로 마감한다 |
| 내부 서버 | `internal/audit.py` | 감사 로그 `<data>/audit.log`(한 줄 JSON). `ctx.log` 의 대상 |
| 외부 서버 | `plugins/english.py` | 오름차순 |
| 외부 서버 | `plugins/sealed_second.py` | 봉인 2차 가격(Vickrey) |
| 외부 서버 | `plugins/dutch.py` | 내림차순 |
| 외부 서버 | `plugins/outbid_notifier.py` | `runtime: "process"`. 밀려난 사람에게 줄 알림 문장을 만든다. 저장·SSE 전송은 코어가 한다 |
| 시연용 | `plugins/broken_type.py` | 기본 미적재. `validate_bid` 에서 예외를 낸다(E3 시연) |
| 시연용 | `plugins/future_contract.py` | `contract: "2.0"` → `rejected` 시연 |
| 예제 | `examples/lowest_unique.py` | 최저 유일가. 사용자가 plugins/ 에 복사해 넣고 설치해 본다(E1) |
| 어댑터 | `adapters/http_adapter.py` | HTTP ↔ 코어 계약, SSE |
| 어댑터 | `adapters/process_adapter.py` | 알림 플러그인 프로세스 ↔ 코어 계약 |

## 경매 규칙 (금액은 정수 원)

| 방식 | 입찰 조건 | 마감 전 공개 | 낙찰 |
|---|---|---|---|
| english | 첫 입찰 ≥ 시작가. 이후 ≥ 현재 최고가 + 증가액. 증가액 = max(1, ceil(시작가 × 0.05)). 현재 최고 입찰자는 다시 입찰할 수 없다 | 모든 입찰 | 마감 때 최고가 입찰자, 그 금액. 입찰이 없으면 유찰 |
| sealed_second | 1인 1회, 금액 ≥ 시작가 | 입찰 수만 | 최고가 입찰자. 동률이면 먼저 낸 사람. 낙찰가 = 두 번째로 높은 금액(입찰 1건이면 시작가). 입찰이 없으면 유찰 |
| dutch | 금액 없이 현재가 수락. 서버가 그 시각의 현재가로 확정 | 현재가 | 첫 수락이 바로 낙찰·마감. 마감까지 수락이 없으면 유찰 |
| lowest_unique(예제) | 금액 ≥ 1, 1인 최대 3회 | 입찰 수만 | 한 사람만 낸 금액 중 가장 낮은 금액과 그 사람. 없으면 유찰 |

- dutch 현재가 = max(바닥가, floor(시작가 − (시작가 − 바닥가) × 경과 / 진행 시간)). 바닥가 = ceil(시작가 × 0.3).
- 규칙 위반은 `Rejected(사유)` 다(장애 아님).

## `auction_type` 확장점 op

| op | in | out |
|---|---|---|
| `validate_bid` | auction, bids, bid, now | `{"amount": int}` 확정 금액(dutch 는 현재가). 위반은 `Rejected` |
| `view` | auction, bids, now | `{"price": int 또는 None, "visible_bids": list, "bid_count": int}` |
| `on_bid_accepted` | auction, bids, bid | `{"close_now": bool, "outbid": str 또는 None}` 밀려난 사람(비공개 방식은 None) |
| `settle` | auction, bids | `{"winner": str 또는 None, "price": int 또는 None}` |

- 자료 모양. 코어가 만들어 넘기고, 시각은 `time.time()` 초다.
  - auction: `{id: str, item: str, start_price: int, duration_sec: int, type: str, status: str, created_at: float, ends_at: float}`. dutch 의 경과 = now − created_at.
  - bid: `{id: str, bidder: str, amount: int 또는 None, created_at: float}`. id 는 코어가 만든다. bidder 는 앞뒤 공백을 뺀 1~20자이고, 비면 코어가 400 으로 거부한다. `validate_bid` 가 받는 bid 는 아직 저장 전이고 dutch 는 amount 가 None 이다. 그 뒤 op 가 받는 bid 에는 확정 금액이 들어 있다.
  - bids: bid 의 list, created_at·id 순.
  - op 별 bids 범위: `validate_bid` = 기존 입찰(새 bid 제외). `on_bid_accepted`, 입찰 경로의 `settle` = 기존 + 새 bid. `view`, 예약 마감의 `settle` = 저장된 전체.
  - `EXTENSION_POINTS` 의 in/out 검사는 최상위 필드만 본다. 중첩 모양은 코어가 만들므로 코어 시험으로 확인한다.
- 플러그인은 저장소를 만지지 않는다. 저장·마감·알림은 코어가 한다.
- `notifier` 확장점 op: `on_outbid`(auction_id, item, user, new_price) → `{"notifications": [{"user", "message"}]}`. 코어는 `outbid` 가 있을 때만 부른다.
- 대상 선택: 경매의 `type` 칸 = 방식 플러그인 이름. 코어는 그 이름의 기록을 찾고 kind 가 `auction_type` 인지 확인한다. notifier 는 `active` 인 notifier 를 모두 부른다.
- ctx 허용 목록: `ctx.log` → `audit.write` 만.

## 코어 절차와 잠금

- 잠금: 경매마다 `threading.Lock` 하나. 같은 잠금을 두 번 잡지 않는다.
- 정산 함수 `_settle_locked(auction, bids)`: 잠금을 이미 잡은 쪽만 부른다. `settle` 을 호출해 상태 변경(`closed` + winner·price, 또는 장애 때 `settle_pending` + 사유)을 돌려준다. 저장은 하지 않는다.
- `now` 는 코어가 요청마다 한 번 정해 같은 값을 모든 op 에 준다.
- 입찰 순서:
  1. 경매 잠금을 잡는다. 상태가 `open` 이고 now < ends_at 인지 확인한다. 아니면 409.
  2. `validate_bid`(bids = 기존 입찰) → 확정 금액으로 새 bid 를 만든다. 아직 저장하지 않는다.
  3. `on_bid_accepted`(bids = 기존 + 새 bid).
  4. `close_now` 면 `_settle_locked(auction, 기존 + 새 bid)`.
  5. 새 bid 와 상태 변경(4 단계가 있었을 때)을 저장소 트랜잭션 하나로 저장한다.
  6. 잠금을 푼다.
  7. `outbid` 가 있으면 notifier 를 부른다(잠금 밖, 시간 제한 있음). 장애는 `notify_error` 로 받아 둔다.
  8. 응답(성공 + `notify_error`)을 보낸다. 그다음 SSE 이벤트를 넣는다.
- 2·3 단계가 `Rejected` 면 400, 장애면 503 이다. 이때는 아무것도 저장하지 않는다.
- 4 단계의 `settle` 이 장애면 입찰은 유효하므로 저장하고, 경매는 `settle_pending` + 사유로 저장한다.
- 예약 마감: 경매 잠금 → `open` 이 아니면 아무것도 하지 않는다(중복 마감 무해) → `_settle_locked(auction, 저장된 전체)` → 상태 변경 저장 → 잠금 해제 → SSE.
- 방식 플러그인이 다시 `active` 가 되면 코어가 그 방식의 `settle_pending` 경매를 같은 잠금 규칙으로 다시 정산한다.
- 상태: `open` → `closed`(낙찰 또는 유찰), `open` → `settle_pending` → `closed`.
- 선택 단계 = 알림. 알림 장애가 나도 입찰은 확정이다. 응답은 성공 + `notify_error` 이고, trace 와 화면에 경고를 보인다. 응답이 알림 호출의 최대 시간(잠금 대기 + 시간 제한 + 정리 2초, 기본 8초)만큼 늦어질 수 있다. README 한계에 적는다.
- remove 거부(409): `open`·`settle_pending` 경매가 쓰는 방식. 장애로 `disabled` 가 되는 것은 막지 않는다. 그동안 그 경매의 입찰은 503.

## 비공개 방식

마감 전에는 목록·상세 JSON·SSE·알림 어디에도 sealed_second·lowest_unique 의 금액과 입찰자를 싣지 않는다(입찰 수만). 코어는 `view` 의 결과만 밖으로 보낸다.

## 도메인 HTTP API

- `POST /api/auctions` `{item, start_price, duration_sec, type}`
- `GET /api/auctions`, `GET /api/auctions/{id}`
- `POST /api/auctions/{id}/bids` `{bidder, amount}` (dutch 는 amount 생략)
- `GET /api/notifications?user=`
- `GET /api/events` SSE: `auction_created`, `bid_accepted`, `auction_closed`, `notification`, `plugin_changed`. 경매 이벤트는 `view` 를 거친 공개 정보만 싣는다.

## 추가 시험

- 네 방식(예제 포함)의 입찰 조건, 낙찰 규칙, 동률, 유찰.
- 1초짜리 경매가 제시간(±0.5초)에 마감된다. 예약이 없을 때 마감 스레드는 timeout 없이 기다린다.
- 새 앱 인스턴스: `open` 경매 재예약, 지난 경매 즉시 마감.
- 동시성: english 에 같은 금액 동시 입찰 20개 → 1개만 수락. dutch 동시 수락 10개 → 낙찰 1개. 마감과 입찰이 겹치면 마감 뒤 입찰은 거부.
- 방식 장애 중 마감 → `settle_pending` → 다시 켜기 → `closed`.
- 알림 플러그인 장애에도 입찰 성공(`notify_error` 표시).
- 비공개 방식: 마감 전 목록·상세·SSE 에 금액·입찰자 없음.
- 진행 중 경매가 쓰는 방식의 remove 거부.
- SSE 구독자 2개가 같은 이벤트를 받는다. 서버를 내리면 구독 연결도 끊기고 시험이 멈추지 않는다.
