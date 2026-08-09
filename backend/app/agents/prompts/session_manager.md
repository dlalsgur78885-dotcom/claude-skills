# Session Manager Agent

## LLM
- **모델**: 없음 (규칙 기반)
- **역할**: LLM 불필요. 세션 CRUD와 상태 관리는 순수 규칙 기반으로 동작.

## 도구/라이브러리
- **redis-py**: Redis 기반 세션 저장/조회/만료 관리
- **FastAPI session middleware**: HTTP 세션 쿠키 처리
- **Pydantic**: 세션 데이터 스키마 검증

## 역할
사용자 세션과 컨텍스트를 관리하고, 개인화된 워크플로우 상태를 추적하며, 비정상 종료 시 작업을 복구하는 세션 관리 에이전트.

## 핵심 책임
1. 세션 생성, 갱신, 만료 관리
2. 사용자 선호 설정(preferences) 저장 및 조회
3. 워크플로우 진행 상태 추적
4. 비정상 종료 시 마지막 상태로 복구
5. 동시 세션 수 제한 및 충돌 방지

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `create_session` | `user_id: str, preferences: dict` | `Session(id, token, expires_at)` |
| `get_session` | `session_id: str` | `Session` |
| `update_preferences` | `session_id: str, prefs: dict` | `Session (갱신됨)` |
| `save_workflow_state` | `session_id: str, state: WorkflowState` | `bool` |
| `restore_session` | `user_id: str` | `Session (복구됨)` |
| `destroy_session` | `session_id: str` | `bool` |

## 의사결정 규칙
- 세션 TTL 기본값: 24시간. 활동 시 자동 연장.
- 동일 사용자 최대 동시 세션: 3개. 초과 시 가장 오래된 세션 만료.
- 워크플로우 상태는 각 단계 완료 시 자동 저장 (체크포인트)
- Redis 연결 실패 시 로컬 메모리 캐시로 fallback (5분 TTL)
- 세션 복구 요청 시 마지막 체크포인트 기준으로 복원
