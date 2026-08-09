# Services — 비즈니스 로직

Worker 에이전트가 호출하는 실제 처리 로직.

## 파일별 역할

- `instagram.py` — HikerAPI 기반 인스타그램 데이터 수집 (REST API, 안정적)
- `playwright_scraper.py` — Playwright 기반 스크래핑 (HikerAPI 불가 시 fallback)
- `scrape_job.py` — 스크래핑 실행 + DB 저장. 중복 체크(instagram_post_id). `run_all_channels()`
- `scheduler.py` — APScheduler 정기 스크래핑 (09:00, 21:00)
- `image_processor.py` — 멀티소스 이미지 검색 + 처리
- `content_gen.py` — LLM 기반 슬라이드 텍스트 생성. Gemini Flash 사용
- `carousel_designer.py` — Fabric.js 캔버스 JSON 생성. 템플릿 로드 + 슬라이드 매핑

## 이미지 소싱 우선순위

**사진**: Pexels → Pixabay → Unsplash → Naver → Bing
**아이콘**: Pixabay(illustration) → Flaticon
**배경제거**: rembg (로컬, 무제한)

## 이미지 검색 API

`GET /api/images/search?q=키워드&style=photo|icon|cutout&limit=12`
