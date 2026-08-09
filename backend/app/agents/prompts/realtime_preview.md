# Realtime Preview Agent

## LLM
- **모델**: 없음 (규칙 기반)
- **역할**: LLM 불필요. 프리뷰 렌더링은 Canvas API와 DOM 조작 기반으로 동작.

## 도구/라이브러리
- **Fabric.js**: `canvas.toDataURL()` 기반 슬라이드 썸네일 생성
- **html-to-image**: DOM 요소를 이미지로 캡처 (모바일 프레임 목업)

## 역할
에디터에서의 변경 사항을 실시간으로 프리뷰에 반영하고, 성능 최적화를 위한 단계별 렌더링과 다양한 프리뷰 모드를 제공하는 에이전트.

## 핵심 책임
1. 슬라이드 변경 시 실시간 썸네일 업데이트
2. 모바일 디바이스 프레임 목업 프리뷰
3. 전체 캐러셀 슬라이드쇼 프리뷰
4. 성능 최적화 (debounce, 저해상도 우선 렌더링)
5. 줌 레벨별 프리뷰 품질 조정

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `render_thumbnail` | `canvas: FabricCanvas, quality: number` | `string (dataURL)` |
| `render_mobile_frame` | `canvas: FabricCanvas, device: string` | `HTMLElement` |
| `start_slideshow` | `slides: List[FabricCanvas], interval: number` | `SlideshowController` |
| `update_preview` | `slide_index: number` | `void` |
| `set_zoom` | `level: number` | `void` |

## 의사결정 규칙
- 편집 중 프리뷰 업데이트는 300ms debounce 적용
- 저해상도 프리뷰 먼저 렌더링 후 고해상도로 교체 (progressive)
- 슬라이드 10개 초과 시 보이는 슬라이드만 렌더링 (가상화)
- 모바일 프레임 목업: iPhone 15 Pro 기본 (375x812 뷰포트)
- 메모리 사용량 100MB 초과 시 오프스크린 캔버스 해제
