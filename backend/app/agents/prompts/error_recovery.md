# Error Recovery Agent

## LLM
- **모델**: 없음 (규칙 기반)
- **역할**: LLM 불필요. 에러 분류와 복구 전략은 사전 정의된 규칙 테이블 기반으로 동작.

## 도구/라이브러리
- **tenacity**: 재시도 로직 (exponential backoff, jitter)
- **pybreaker**: 서킷 브레이커 패턴 구현
- **structlog**: 구조화된 에러 로깅

## 역할
시스템 전반에서 발생하는 에러를 분류하고, 자동 복구를 시도하며, 복구 불가 시 적절한 대체 워크플로우를 실행하거나 에스컬레이션하는 에이전트.

## 핵심 책임
1. 에러 유형 분류 (transient, permanent, partial)
2. 재시도 전략 실행 (tenacity 기반)
3. 서킷 브레이커 상태 관리 (closed → open → half-open)
4. 대체 경로(fallback) 라우팅
5. 에러 이력 기록 및 패턴 분석

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `classify_error` | `error: Exception, context: dict` | `ErrorClass(type, severity, retryable)` |
| `retry_task` | `task_id: str, strategy: RetryStrategy` | `TaskResult \| ErrorEscalation` |
| `trigger_fallback` | `task_id: str, fallback_config: dict` | `FallbackResult` |
| `check_circuit` | `service_name: str` | `CircuitState(closed\|open\|half_open)` |
| `escalate` | `error: ErrorClass, attempts: int` | `EscalationTicket` |

## 의사결정 규칙
- Transient 에러 (timeout, 429): 최대 3회 재시도, exponential backoff (1s, 2s, 4s)
- Permanent 에러 (401, 404): 즉시 에스컬레이션, 재시도 없음
- Partial 에러 (일부 슬라이드만 실패): 실패분만 재시도
- 서킷 브레이커: 5분 내 5회 실패 시 open. 30초 후 half-open으로 전환.
- fallback 순서: 대체 API → 캐시된 결과 → 사용자 알림
- 동일 에러가 10분 내 10회 반복 시 health_monitor에 알림
