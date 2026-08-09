# Asset Manager Agent

## LLM
- **모델**: GPT-4o-mini (`gpt-4o-mini`)
- **역할**: 이미지 자동 태깅 및 설명 생성. GPT-4o-mini를 사용하는 이유는 멀티모달(이미지 인식) 지원하면서도 태깅 같은 경량 작업에 비용 효율적이기 때문.

## 도구/라이브러리
- **Pillow**: 이미지 메타데이터 읽기, 썸네일 생성, 포맷 변환
- **Cloudinary** (optional): 클라우드 에셋 저장소 및 CDN
- **LiteLLM**: GPT-4o-mini 모델 호출 (자동 태깅)
- **Pydantic**: 에셋 메타데이터 스키마 검증

## 역할
이미지, 아이콘, 배경 등 디자인 에셋을 체계적으로 관리하고, AI 자동 태깅/검색/리사이즈를 제공하며 라이선스를 추적하는 에이전트.

## 핵심 책임
1. 에셋 업로드, 저장, 조회, 삭제 (CRUD)
2. AI 기반 자동 태깅 (GPT-4o-mini 멀티모달)
3. 키워드/태그 기반 에셋 검색
4. 썸네일 생성 및 다양한 크기 변환
5. 라이선스 타입 추적 (free, commercial, editorial)

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `upload_asset` | `file: UploadFile, category: str, license: str` | `Asset(id, url, tags)` |
| `auto_tag` | `asset_id: str` | `List[Tag(name, confidence)]` |
| `search_assets` | `query: str, category: Optional[str], limit: int` | `List[Asset]` |
| `get_asset` | `asset_id: str, size: Optional[str]` | `Asset` |
| `delete_asset` | `asset_id: str` | `bool` |
| `bulk_import` | `source_dir: str, category: str` | `ImportResult(imported, skipped, errors)` |

## 의사결정 규칙
- 업로드 시 자동 태깅 실행 (confidence 0.7 이상만 저장)
- 중복 이미지 감지 시 기존 에셋 참조로 대체 (perceptual hash 비교)
- Cloudinary 연결 불가 시 로컬 스토리지 fallback
- 에셋 파일 크기 10MB 초과 시 자동 압축
- 라이선스 미확인 에셋은 `editorial` 태그 부여 (상업 사용 제한 경고)
