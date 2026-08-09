# Template Manager Agent

## LLM
- **모델**: Gemini Flash (`gemini-flash`)
- **역할**: 콘텐츠 분석 기반 템플릿 추천. Gemini Flash를 사용하는 이유는 빠른 분류/매칭 작업에 적합하고 비용 효율적이기 때문.

## 도구/라이브러리
- **Jinja2**: 템플릿 렌더링 엔진 (변수 치환, 조건부 블록, 반복)
- **Pydantic**: 템플릿 메타데이터 및 스키마 검증
- **LiteLLM**: Gemini Flash 모델 호출 (추천 기능)

## 역할
캐러셀 템플릿의 생성, 수정, 삭제, 버전 관리를 담당하고, 사용자 맥락에 맞는 템플릿을 추천하는 에이전트.

## 핵심 책임
1. 템플릿 CRUD (생성, 조회, 수정, 삭제)
2. 템플릿 버전 관리 (이전 버전 보존)
3. 콘텐츠 분석 기반 스마트 추천 (LLM 활용)
4. 템플릿 변수 스키마 정의 및 검증
5. 카테고리별 템플릿 분류 및 검색

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `create_template` | `name: str, jinja_source: str, schema: dict, category: str` | `Template(id, version)` |
| `get_template` | `template_id: str, version: Optional[int]` | `Template` |
| `update_template` | `template_id: str, updates: dict` | `Template (새 버전)` |
| `delete_template` | `template_id: str` | `bool` |
| `recommend` | `content: CarouselContent, count: int` | `List[TemplateRecommendation(id, score, reason)]` |
| `list_templates` | `category: Optional[str], page: int` | `PaginatedList[Template]` |

## 의사결정 규칙
- 추천 시 콘텐츠 슬라이드 수, 이미지 유무, 톤앤매너를 분석하여 매칭
- 사용자가 이전에 선택한 템플릿이 있으면 가중치 부여
- 템플릿 수정 시 기존 버전은 보존 (비파괴 업데이트)
- 30일간 사용되지 않은 사용자 커스텀 템플릿에 정리 알림
- 시스템 기본 템플릿은 삭제 불가
