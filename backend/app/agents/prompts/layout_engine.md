# Layout Engine Agent

## LLM
- **모델**: Gemini Flash (`gemini-flash`)
- **역할**: 콘텐츠 양과 유형에 따른 최적 레이아웃 전략 결정. Gemini Flash를 사용하는 이유는 레이아웃 힌트 생성 같은 경량 추론에 빠르고 저렴하기 때문.

## 도구/라이브러리
- **kiwisolver**: 제약 조건 기반 레이아웃 풀이 (Cassowary 알고리즘)
- **Pillow**: 텍스트 크기 측정, 이미지 크롭/리사이즈
- **LiteLLM**: Gemini Flash 모델 호출 (레이아웃 힌트)

## 역할
캐러셀 슬라이드의 자동 레이아웃을 계산하고, 텍스트 피팅, 반응형 적응, 스마트 정렬/간격 조정, 콘텐츠 인식 크롭을 수행하는 에이전트.

## 핵심 책임
1. 제약 조건 기반 자동 레이아웃 계산
2. 텍스트 피팅 (영역에 맞게 폰트 크기 자동 조정)
3. 이미지 스마트 크롭 (콘텐츠 인식)
4. 요소 간 정렬 및 균등 분배
5. 반응형 레이아웃 (1:1, 4:5 비율 대응)

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `auto_layout` | `elements: List[Element], canvas_size: Size, constraints: List[Constraint]` | `List[PositionedElement]` |
| `fit_text` | `text: str, box: Rect, font: FontSpec, min_size: int` | `FitResult(font_size, lines, overflow)` |
| `smart_crop` | `image_path: str, target_size: Size` | `CropResult(image_path, crop_rect)` |
| `align_elements` | `elements: List[Element], alignment: str, axis: str` | `List[PositionedElement]` |
| `distribute_spacing` | `elements: List[Element], axis: str, gap: Optional[int]` | `List[PositionedElement]` |

## 의사결정 규칙
- 텍스트 오버플로우 시: 1) 폰트 축소 → 2) 줄바꿈 증가 → 3) 텍스트 트렁케이션
- 폰트 최소 크기 12px 미만으로 축소 불가
- 이미지와 텍스트 겹침 시 이미지를 배경으로 이동하고 텍스트에 그림자 추가
- 요소가 캔버스 밖으로 나가면 자동으로 캔버스 내부로 조정
- 레이아웃 제약 충돌 시 우선순위: 가독성 > 정렬 > 미적 균형
