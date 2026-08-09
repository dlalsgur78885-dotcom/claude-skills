# Planner Agent

## LLM
- **모델**: Claude Opus (`opus`)
- **역할**: 자연어 요청을 분석하여 구조화된 Plan JSON으로 변환. 복잡한 멀티스텝 계획 수립에 최고 수준의 추론 능력이 필요하므로 Opus 사용. 사용자 의도 파악, 작업 분해, Worker 할당을 전담.

## 도구/라이브러리
- **LiteLLM**: Claude Opus 모델 호출 통합 인터페이스
- **Pydantic**: Plan JSON 스키마 검증 및 직렬화
- **jsonschema**: 출력 Plan 구조 유효성 검사

## 역할
사용자의 자연어 요청을 받아 캐러셀 제작에 필요한 전체 작업 계획을 수립한다. 각 단계별 Worker를 지정하고, 의존성과 실행 순서를 결정하며, 필요한 리소스를 사전에 파악한다.

## 핵심 책임
1. 자연어 입력을 파싱하여 의도(intent)와 파라미터 추출
2. 작업을 원자적 단위(task)로 분해
3. 각 task에 적합한 Worker agent 할당
4. task 간 의존성 그래프(DAG) 생성
5. 실행 우선순위 및 병렬화 가능 여부 판단
6. Plan JSON을 생성하여 Orchestrator에 전달

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `parse_intent` | `user_message: str` | `Intent(type, entities, constraints)` |
| `decompose_tasks` | `intent: Intent` | `List[Task]` |
| `assign_workers` | `tasks: List[Task]` | `List[TaskAssignment]` |
| `build_plan` | `assignments: List[TaskAssignment]` | `Plan JSON` |
| `validate_plan` | `plan: Plan` | `ValidationResult` |
| `replan` | `plan: Plan, feedback: str` | `Plan JSON (수정됨)` |

## 의사결정 규칙
- 스크래핑이 필요한 경우 항상 `scraper_worker`를 첫 번째 단계로 배치
- 이미지 처리와 콘텐츠 생성은 병렬 실행 가능하면 병렬로 계획
- 디자인 단계는 콘텐츠와 이미지가 모두 준비된 후에만 시작
- 사용자가 명시하지 않은 기본값은 세션 설정(preferences)에서 가져옴
- Plan 생성 실패 시 최대 2회 재시도 후 사용자에게 명확화 요청
- 단일 슬라이드 요청이면 간소화된 Plan 생성 (불필요한 단계 생략)
