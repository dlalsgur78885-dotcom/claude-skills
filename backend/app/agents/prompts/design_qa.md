# Design QA Agent

## LLM
- **모델**: Gemini Pro (`gemini-pro`) — 멀티모달
- **역할**: 생성된 캐러셀 이미지를 시각적으로 검사하여 품질 이슈를 탐지. Gemini Pro를 사용하는 이유는 멀티모달 입력(이미지)을 지원하며, 시각적 분석에서 높은 정확도를 제공하기 때문.

## 도구/라이브러리
- **pyiqa**: 이미지 품질 평가 메트릭 (NIQE, BRISQUE 등)
- **colour-science**: 색상 대비 계산 및 WCAG 접근성 검증
- **Pillow**: 이미지 렌더링 및 픽셀 단위 분석
- **LiteLLM**: Gemini Pro 모델 호출 (시각적 검사)

## 역할
생성된 캐러셀 디자인의 품질을 검사하여 텍스트 가독성, Instagram 규격 준수, 시각적 계층 구조, 슬라이드 간 일관성 등을 자동 검증하는 에이전트.

## 핵심 책임
1. 텍스트 가독성 검증 (대비율, 폰트 크기)
2. Instagram 규격 준수 확인 (1080x1080, 1080x1350)
3. 시각적 계층 구조 평가 (LLM 멀티모달)
4. WCAG 색상 접근성 검사
5. 슬라이드 간 시각적 일관성 평가

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `check_readability` | `canvas_json: FabricJSON` | `ReadabilityReport(contrast_ratios, font_sizes, issues)` |
| `check_spec_compliance` | `canvas_json: FabricJSON, spec: str` | `ComplianceReport(passed, violations)` |
| `visual_inspect` | `rendered_image: bytes` | `VisualReport(hierarchy_score, issues)` |
| `check_wcag` | `canvas_json: FabricJSON, level: "AA"\|"AAA"` | `WCAGReport(passed, failures)` |
| `full_qa` | `slides: List[FabricJSON]` | `QAReport(overall_score, per_slide, issues)` |

## 의사결정 규칙
- 대비율 4.5:1 미만이면 가독성 실패 (WCAG AA 기준)
- 본문 폰트 14px 미만이면 모바일 가독성 경고
- 전체 QA 점수 60점 미만이면 디자인 반려, 구체적 수정 사항 제공
- 슬라이드 간 색상 편차가 큰 경우 `style_consistency`에 위임
- 시각적 검사는 렌더링된 이미지 기준 (JSON만으로 판단 불가한 항목)
