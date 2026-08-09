# 필요 API 레퍼런스

## 1. Instagram 데이터 - HikerAPI (핵심)
- **URL**: https://hikerapi.com
- **문서**: https://api.hikerapi.com/docs
- **가격**: $0.0006~$0.02/요청 (패키지별)
- **147개 엔드포인트**, 속도제한 없음

### 우리가 쓸 핵심 엔드포인트
| 엔드포인트 | 용도 |
|-----------|------|
| `GET /user/by/username/{username}` | 채널 프로필 조회 |
| `GET /user/{user_id}/medias` | 채널 포스트 목록 |
| `GET /media/by/shortcode/{shortcode}` | 개별 포스트 상세 (캐러셀 슬라이드 포함) |
| `GET /media/{media_id}/comments` | 댓글 수집 |
| `GET /hashtag/{name}/medias` | 해시태그 탐색 (채널 발견) |
| `GET /user/{user_id}/followers` | 팔로워 분석 |
| `GET /search` | 채널/해시태그 검색 |

→ **Playwright 스크래핑을 HikerAPI로 대체** (훨씬 안정적, 안티봇 걱정 없음)

---

## 2. AI/LLM - 텍스트 생성
| API | 용도 | 가격 |
|-----|------|------|
| **Google Gemini** (현재 설정) | 슬라이드 텍스트 생성 | Flash: 무료~$0.075/M 토큰 |
| **Claude API** (대안) | 고품질 텍스트 | Haiku: $0.25/$1.25/M 토큰 |
| **OpenAI** (대안) | GPT-4o-mini | $0.15/$0.60/M 토큰 |

→ 현재 Google GenAI 유지, 필요시 Claude로 업그레이드

---

## 3. 투명 이미지 소싱 (누끼) — 핵심 전략 변경!

**기본 전략: 처음부터 누끼 이미지를 가져온다 (후처리 X)**

| 우선순위 | API | 용도 | 가격 |
|---------|-----|------|------|
| 1순위 | **Pixabay** (`colors=transparent`) | 투명 스톡 이미지 검색 | 무료 (100req/분) |
| 2순위 | **Flaticon** | 투명 아이콘/일러스트 | 무료 티어 |
| 3순위 | **OpenAI GPT-Image** (`background="transparent"`) | AI로 누끼 이미지 생성 | $0.01~0.17/장 |
| 폴백 | **rembg** (로컬) | 기존 이미지 배경 제거 | 무료 |
| 폴백 | **remove.bg** (API) | 고품질 배경 제거 | 50장/월 무료 |

### Pixabay 투명 검색 예시
```
GET https://pixabay.com/api/?key=KEY&q=coffee&colors=transparent&image_type=illustration
```

### OpenAI 투명 이미지 생성 예시
```json
POST https://api.openai.com/v1/images/generations
{
  "model": "gpt-image-1",
  "prompt": "커피잔 누끼 사진",
  "background": "transparent",
  "output_format": "png"
}
```

---

## 4. 스톡 이미지
| API | 용도 | 가격 |
|-----|------|------|
| **Unsplash API** | 무료 고화질 사진 | 무료 (50req/시간) |
| **Pexels API** | 무료 고화질 사진 | 무료 (200req/시간) |

→ 캐러셀에 넣을 배경/소재 이미지 검색용

---

## 5. 폰트
| API | 용도 | 가격 |
|-----|------|------|
| **Google Fonts** | 한글 웹폰트 | 무료 |
| **Pretendard CDN** | 기본 한글 폰트 | 무료 |

→ 한국어 폰트: https://googlefonts.github.io/korean/

---

## 6. 저장소/인증
| API | 용도 | 가격 |
|-----|------|------|
| **Supabase** | DB + 스토리지 + Auth | 무료 (500MB DB, 1GB 스토리지) |
| **Cloudinary** | 이미지 CDN + 변환 | 무료 (25GB 스토리지) |

→ MVP는 로컬 SQLite + 파일시스템, 스케일 시 Supabase/Cloudinary

---

## 7. 인스타그램 게시 (퍼블리싱)
| API | 용도 | 가격 |
|-----|------|------|
| **Instagram Graph API** | 캐러셀 직접 게시 | 무료 (Meta 비즈니스 계정 필요) |

### 퍼블리싱 엔드포인트
```
POST /{ig-user-id}/media           # 슬라이드 컨테이너 생성
POST /{ig-user-id}/media_publish   # 캐러셀 게시
GET /{ig-user-id}/content_publishing_limit  # 게시 제한 확인
```
→ Meta 비즈니스/크리에이터 계정 + Facebook 페이지 연결 필요

---

## 8. 기타
| API | 용도 | 가격 |
|-----|------|------|
| **DeepL** | 다국어 번역 | 500K 자/월 무료 |
| **Auth.js** | 소셜 로그인 | 무료 (라이브러리) |

---

## 월간 예상 비용 (MVP)

| 서비스 | 예상 사용량 | 비용 |
|--------|-----------|------|
| HikerAPI | ~10,000 요청 | ~$6 |
| Google Gemini Flash | ~500K 토큰 | 무료 |
| remove.bg | 50장 이내 | 무료 |
| Unsplash/Pexels | 무제한 | 무료 |
| Instagram Graph API | 게시용 | 무료 |
| **합계** | | **~$6/월** |

---

## 환경변수 (.env)
```
# HikerAPI
HIKER_API_KEY=your-hiker-api-key
HIKER_API_BASE_URL=https://api.hikerapi.com

# AI
GOOGLE_API_KEY=your-google-genai-key

# Image
REMOVEBG_API_KEY=your-removebg-key

# Stock Images
UNSPLASH_ACCESS_KEY=your-unsplash-key
PEXELS_API_KEY=your-pexels-key

# Instagram Publishing
META_APP_ID=your-meta-app-id
META_APP_SECRET=your-meta-app-secret
INSTAGRAM_ACCESS_TOKEN=your-ig-access-token

# Auth
SECRET_KEY=your-jwt-secret
```
