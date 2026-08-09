# Evaluator Agent

## LLM
- **모델**: Consensus of 3 models — Claude Opus (`opus`), Gemini Flash Thinking (`gemini-flash-thinking`), o3-mini (`o3-mini`)
- **역할**: 각 모델이 독립적으로 채점 후 가중 평균으로 최종 점수 산출. Opus는 깊은 분석과 뉘앙스 평가, Gemini Thinking은 추론 체인 기반 논리 검증, o3-mini는 코드/구조적 논리 검증 담당. 3개 모델 합의로 단일 모델 편향을 방지.

## 도구/라이브러리
- **LiteLLM**: 멀티 모델 동시 호출 인터페이스
- **numpy**: 가중 평균 점수 계산
- **Pydantic**: 평가 결과 스키마 정의 및 검증

## 역할
Planner가 수립한 계획의 실행 결과를 검증하고, 품질을 평가하여 Planner에게 피드백을 제공하는 품질 관리 에이전트. 콘텐츠 품질, 디자인 적합성, 브랜드 일관성을 다각도로 심사한다.

## 핵심 책임
1. 생성된 콘텐츠의 품질 점수 산출 (0-100)
2. 3개 LLM의 독립 평가 결과를 가중 평균으로 합산
3. 기준 미달 항목에 대한 구체적 개선 피드백 생성
4. 반복 평가 시 이전 점수 대비 개선도 추적
5. 최종 승인/반려 결정

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `evaluate_content` | `content: CarouselContent, criteria: List[str]` | `EvalResult(scores, feedback)` |
| `evaluate_design` | `design_json: FabricJSON, brand_guide: BrandGuide` | `EvalResult(scores, feedback)` |
| `consensus_score` | `model_scores: Dict[str, float]` | `float (가중 평균)` |
| `approve_or_reject` | `eval_result: EvalResult, threshold: float` | `Decision(approved: bool, reasons)` |
| `generate_feedback` | `eval_result: EvalResult` | `List[ImprovementSuggestion]` |

## 의사결정 규칙
- 가중치: Opus 0.4, Gemini Thinking 0.35, o3-mini 0.25
- 3개 모델 점수 편차가 20점 이상이면 재평가 트리거
- 최종 점수 70점 미만이면 자동 반려 + 개선 피드백 전달
- 최종 점수 70-85점이면 조건부 승인 (경미한 수정 제안)
- 최종 점수 85점 이상이면 무조건 승인
- 평가 요청당 최대 3회 반복 (무한 루프 방지)
