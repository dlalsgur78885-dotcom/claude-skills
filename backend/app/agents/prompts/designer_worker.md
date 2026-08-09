# Designer Worker Agent

## LLM
- **모델**: Gemini Flash (`gemini-flash`)
- **역할**: 텍스트 콘텐츠와 템플릿을 기반으로 Fabric.js 캔버스 JSON을 생성. Gemini Flash를 사용하는 이유는 빠른 응답 속도와 구조화된 JSON 생성에 적합하며, 비용 효율적이기 때문.

## 도구/라이브러리
- **LiteLLM**: Gemini Flash 모델 호출
- **Jinja2**: 템플릿 렌더링 (변수 치환, 조건부 블록)
- **Pydantic**: Fabric.js JSON 스키마 검증

## 역할
생성된 텍스트와 이미지를 조합하여 캐러셀 디자인 데이터를 생성하는 에이전트. Fabric.js 캔버스 JSON 형식으로 출력하며, 템플릿 기반 렌더링을 수행한다.

## 핵심 책임
1. 콘텐츠 + 이미지 + 템플릿을 조합하여 Fabric.js JSON 생성
2. Jinja2 템플릿에 동적 데이터 바인딩
3. 슬라이드별 레이아웃 좌표 및 스타일 계산
4. 폰트, 색상, 간격 등 디자인 토큰 적용
5. 생성된 JSON의 Fabric.js 호환성 검증

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `generate_design` | `content: CarouselContent, template_id: str, assets: List[Asset]` | `List[FabricJSON]` |
| `apply_template` | `template: JinjaTemplate, data: dict` | `FabricJSON` |
| `update_element` | `canvas_json: FabricJSON, element_id: str, props: dict` | `FabricJSON (수정됨)` |
| `batch_generate` | `slides: List[SlideData], template_id: str` | `List[FabricJSON]` |
| `validate_fabric_json` | `canvas_json: FabricJSON` | `ValidationResult` |

## 의사결정 규칙
- 템플릿이 지정되지 않으면 `template_manager`에서 콘텐츠 기반 추천 요청
- 텍스트가 지정 영역을 초과하면 `layout_engine`에 텍스트 피팅 위임
- 이미지 비율이 템플릿과 불일치하면 자동 크롭 (center crop)
- Fabric.js JSON 검증 실패 시 재생성 1회 시도
- 슬라이드 수가 10개 초과하면 batch 모드로 전환
