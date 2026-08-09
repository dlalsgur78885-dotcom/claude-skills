# Scraper Worker Agent

## LLM
- **모델**: 없음 (규칙 기반)
- **역할**: LLM 불필요. REST API 호출과 데이터 파싱만 수행하므로 규칙 기반으로 동작.

## 도구/라이브러리
- **HikerAPI**: Instagram 데이터 수집 REST API 서비스
- **httpx**: 비동기 HTTP 클라이언트 (API 호출)
- **Pydantic**: 스크래핑 결과 데이터 모델 검증

## 역할
Instagram에서 벤치마크 채널의 포스트, 이미지, 캡션, 해시태그 등을 수집하는 스크래핑 전문 에이전트. HikerAPI를 통해 안정적으로 데이터를 가져온다.

## 핵심 책임
1. Instagram 프로필/포스트 데이터를 HikerAPI로 수집
2. 수집된 데이터를 정규화하여 표준 포맷으로 변환
3. 이미지 URL 추출 및 유효성 검증
4. Rate limiting 준수 및 API 쿼터 관리
5. 수집 실패 시 재시도 또는 에러 보고

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `scrape_profile` | `username: str` | `ProfileData(bio, followers, post_count)` |
| `scrape_posts` | `username: str, limit: int, offset: int` | `List[PostData]` |
| `scrape_single_post` | `post_url: str` | `PostData(images, caption, hashtags, likes)` |
| `download_images` | `image_urls: List[str], output_dir: str` | `List[LocalImagePath]` |
| `validate_data` | `raw_data: dict` | `ValidatedData` |

## 의사결정 규칙
- API rate limit 초과 시 exponential backoff (1s, 2s, 4s, 최대 30s)
- 이미지 URL이 만료된 경우 재요청 1회 시도
- 단일 요청 실패 시 최대 3회 재시도
- 수집 데이터가 비어있으면 `error_recovery` 에이전트에 에스컬레이션
- 프로필이 비공개인 경우 즉시 사용자에게 알림 반환
