# Image Processor Worker Agent

## LLM
- **모델**: 없음 (규칙 기반)
- **역할**: LLM 불필요. 이미지 처리 파이프라인은 API 호출과 라이브러리 기반으로 동작.

## 도구/라이브러리
- **Pixabay API**: 무료 스톡 이미지 검색 및 다운로드
- **Flaticon API**: 아이콘/일러스트 검색 및 다운로드
- **OpenAI GPT-Image API**: AI 이미지 생성 (투명 배경 PNG 포함)
- **rembg**: 배경 제거 (누끼) 처리
- **Pillow**: 이미지 리사이즈, 포맷 변환, 메타데이터 처리

## 역할
캐러셀에 사용할 투명 배경 이미지를 소싱하는 파이프라인 에이전트. Pixabay/Flaticon에서 검색 후 없으면 GPT-Image로 생성하며, 필요 시 rembg로 배경을 제거한다.

## 핵심 책임
1. 키워드 기반 이미지 소싱 (Pixabay → Flaticon → GPT-Image 순서)
2. 배경 제거 (rembg) 및 투명 PNG 변환
3. 캐러셀 규격에 맞는 리사이즈 (1080x1080, 1080x1350)
4. 이미지 품질 검증 (해상도, 파일 크기, 투명도)
5. 처리된 이미지를 임시 저장소에 캐싱

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `search_stock` | `query: str, source: "pixabay"\|"flaticon", limit: int` | `List[ImageResult]` |
| `generate_image` | `prompt: str, size: str, transparent: bool` | `GeneratedImage(url, local_path)` |
| `remove_background` | `image_path: str` | `str (투명 PNG 경로)` |
| `resize_image` | `image_path: str, width: int, height: int, fit: str` | `str (리사이즈된 이미지 경로)` |
| `validate_image` | `image_path: str, requirements: ImageReqs` | `ValidationResult` |

## 의사결정 규칙
- 소싱 우선순위: Pixabay (무료) → Flaticon (아이콘) → GPT-Image (생성)
- Pixabay/Flaticon에서 결과가 3개 미만이면 다음 소스로 이동
- 배경이 단색(90% 이상 동일 컬러)이면 rembg 대신 색상 키잉 사용
- 이미지 해상도가 500px 미만이면 품질 부적합으로 폐기
- GPT-Image 생성 실패 시 1회 프롬프트 수정 후 재시도
