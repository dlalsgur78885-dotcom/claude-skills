# Export Publisher Agent

## LLM
- **모델**: 없음 (규칙 기반)
- **역할**: LLM 불필요. 내보내기와 발행은 파일 변환과 API 호출로 동작.

## 도구/라이브러리
- **Pillow**: PNG/JPEG 이미지 렌더링 및 최적화
- **WeasyPrint**: HTML/CSS → PDF 변환 (캐러셀 PDF 내보내기)
- **Instagram Graph API**: Instagram 피드/스토리에 직접 발행

## 역할
완성된 캐러셀을 다양한 포맷으로 내보내고, Instagram에 직접 발행하며, 배치 내보내기와 내보내기 이력을 관리하는 에이전트.

## 핵심 책임
1. 다중 포맷 내보내기 (PNG, JPEG, PDF)
2. Instagram 피드/스토리 직접 발행
3. 배치 내보내기 (전체 슬라이드 일괄 처리)
4. 이미지 품질/용량 최적화
5. 내보내기/발행 이력 기록

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `export_images` | `slides: List[FabricJSON], format: "png"\|"jpeg", quality: int` | `List[ExportedFile(path, size)]` |
| `export_pdf` | `slides: List[FabricJSON], layout: str` | `ExportedFile(path, size)` |
| `publish_instagram` | `images: List[str], caption: str, hashtags: List[str]` | `PublishResult(post_id, url)` |
| `batch_export` | `project_id: str, formats: List[str]` | `BatchResult(files, total_size)` |
| `get_export_history` | `project_id: str, limit: int` | `List[ExportRecord]` |

## 의사결정 규칙
- PNG: 투명 배경 필요 시. JPEG: 파일 크기 최적화 필요 시 (quality 85 기본).
- Instagram 발행 전 이미지 규격 자동 검증 (1080px, 1:1 또는 4:5)
- 단일 이미지 5MB 초과 시 자동 압축
- PDF 내보내기 시 슬라이드 순서대로 페이지 배치
- Instagram API 토큰 만료 시 사용자에게 재인증 요청
- 발행 실패 시 로컬에 백업 저장 후 재시도 안내
