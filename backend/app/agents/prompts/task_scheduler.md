# Task Scheduler Agent

## LLM
- **모델**: 없음 (규칙 기반)
- **역할**: LLM 불필요. 작업 큐잉과 스케줄링은 규칙 기반 우선순위와 CRON 표현식으로 동작.

## 도구/라이브러리
- **arq**: Redis 기반 비동기 작업 큐 (Worker 프로세스 관리)
- **APScheduler**: CRON 스케줄링, 주기적 작업 등록
- **redis-py**: 작업 큐 백엔드 및 rate limiting 카운터

## 역할
작업 큐를 관리하고, 우선순위에 따라 작업을 스케줄링하며, rate limiting과 동시성을 제어하여 시스템 자원을 효율적으로 배분하는 에이전트.

## 핵심 책임
1. 작업 큐 enqueue/dequeue 관리
2. 우선순위 기반 작업 정렬 및 실행
3. Rate limiting (API별, 사용자별)
4. CRON 기반 정기 작업 등록/실행
5. 동시 실행 작업 수 제한 (concurrency control)

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `enqueue_task` | `task: Task, priority: int, delay: Optional[int]` | `TaskTicket(id, position, eta)` |
| `cancel_task` | `task_id: str` | `bool` |
| `get_queue_status` | `queue_name: str` | `QueueStatus(pending, active, completed)` |
| `schedule_cron` | `job_name: str, cron_expr: str, task: Task` | `CronJob(id, next_run)` |
| `set_rate_limit` | `key: str, max_calls: int, period: int` | `RateLimitConfig` |

## 의사결정 규칙
- 우선순위: 사용자 대화형 요청(P1) > 자동 생성(P2) > 배치 작업(P3) > 유지보수(P4)
- 동시 실행 최대: Worker당 5개, 시스템 전체 20개
- HikerAPI rate limit: 분당 30회. 초과 시 큐에 대기.
- LLM API rate limit: 모델별 분당 토큰 한도 적용
- 큐 길이가 100개 초과 시 P4 작업 자동 지연
- CRON 작업 실행 실패 시 다음 스케줄에 재시도
