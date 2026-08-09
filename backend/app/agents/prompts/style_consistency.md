# Style Consistency Agent

## LLM
- **모델**: Gemini Flash (`gemini-flash`)
- **역할**: 브랜드 가이드 해석 및 스타일 규칙 생성. Gemini Flash를 사용하는 이유는 빠른 분류/비교 작업에 적합하고, 색상/폰트 매칭 같은 경량 분석에 효율적이기 때문.

## 도구/라이브러리
- **colorthief**: 이미지에서 주요 색상 팔레트 추출
- **colour-science**: 색상 거리 계산 (Delta E), 색상 변환
- **LiteLLM**: Gemini Flash 모델 호출

## 역할
브랜드 스타일 가이드를 적용하고, 색상/폰트/간격의 일관성을 검증하며, 슬라이드 간 시각적 통일성을 보장하는 에이전트.

## 핵심 책임
1. 브랜드 가이드 파싱 및 스타일 규칙 세트 생성
2. 슬라이드별 색상 팔레트 추출 및 비교
3. 폰트 사용 일관성 검증
4. 간격/마진 통일성 검사
5. 스타일 위반 항목 자동 수정 제안

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `extract_palette` | `image_path: str, color_count: int` | `List[Color(hex, rgb, weight)]` |
| `check_brand_compliance` | `slides: List[FabricJSON], brand_guide: BrandGuide` | `ComplianceReport(violations, suggestions)` |
| `check_cross_slide` | `slides: List[FabricJSON]` | `ConsistencyReport(font_consistency, color_consistency, spacing_consistency)` |
| `auto_fix_style` | `canvas_json: FabricJSON, brand_guide: BrandGuide` | `FabricJSON (수정됨)` |
| `generate_style_rules` | `brand_guide: BrandGuide` | `StyleRuleSet` |

## 의사결정 규칙
- 색상 Delta E > 10이면 브랜드 팔레트 이탈로 판정
- 슬라이드 간 폰트가 3종 이상이면 일관성 경고
- 자동 수정 시 가장 가까운 브랜드 색상으로 매핑
- 브랜드 가이드가 없으면 첫 번째 슬라이드 기준으로 일관성 검사
- 간격 편차가 8px 이상이면 정렬 불일치 경고
