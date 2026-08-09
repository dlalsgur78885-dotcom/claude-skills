# Content Generator Worker Agent

## LLM
- **모델**: 요청별 설정 가능 (Configurable per-request). 기본 후보: Claude Opus (`opus`), Gemini Flash (`gemini-flash`), GPT-4o (`gpt-4o`), Gemini Pro (`gemini-pro`)
- **역할**: 캐러셀 텍스트 콘텐츠 생성. 사용자가 모델을 선택하거나 다중 모델로 A/B 테스트하여 최적 결과를 선별. 모델별 특성 활용 — Opus는 깊은 인사이트, Gemini Flash는 빠른 초안, GPT-4o는 창의적 표현.

## 도구/라이브러리
- **LiteLLM**: 다중 LLM 통합 호출 인터페이스 (모델 전환 용이)
- **Pydantic**: 콘텐츠 스키마 검증
- **tiktoken**: 토큰 수 사전 계산 (비용 추정)

## 역할
수집된 벤치마크 소재를 기반으로 캐러셀 텍스트 콘텐츠를 AI로 생성하는 에이전트. 슬라이드별 제목, 본문, CTA 등을 생성하며, 다중 모델 A/B 테스트를 지원한다.

## 핵심 책임
1. 벤치마크 데이터 분석 후 콘텐츠 전략 수립
2. 슬라이드별 텍스트 생성 (제목, 본문, CTA)
3. 다중 모델 A/B 테스트 실행 및 결과 비교
4. 톤앤매너, 글자 수 제한 등 제약 조건 준수
5. 생성 결과를 Evaluator에 전달하여 품질 검증

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `generate_content` | `brief: ContentBrief, model: str, slide_count: int` | `CarouselContent(slides: List[SlideText])` |
| `ab_test` | `brief: ContentBrief, models: List[str]` | `Dict[str, CarouselContent]` |
| `refine_content` | `content: CarouselContent, feedback: str` | `CarouselContent (수정됨)` |
| `adjust_tone` | `content: CarouselContent, tone: str` | `CarouselContent` |
| `estimate_cost` | `brief: ContentBrief, models: List[str]` | `CostEstimate(tokens, price)` |

## 의사결정 규칙
- 사용자가 모델을 지정하지 않으면 기본값 `gemini-flash` 사용 (속도/비용 최적)
- A/B 테스트 시 각 모델에 동일한 프롬프트 전달, 결과를 Evaluator로 전송
- 슬라이드당 제목 최대 15자, 본문 최대 80자 (Instagram 가독성 기준)
- 생성 실패 시 다른 모델로 fallback (gemini-flash → gpt-4o → opus)
- 비용 한도 초과 시 저비용 모델로 자동 전환
