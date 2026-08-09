# API — REST 엔드포인트

모든 라우터는 `router.py`에서 `/api` prefix로 통합.

## 엔드포인트별 파일

- `auth.py` — 인증 (signup, login, me). JWT Bearer. 첫 가입 = admin
- `channels.py` — 벤치마크 채널 CRUD
- `posts.py` — 수집된 포스트 조회. 좋아요/댓글/날짜 필터링
- `carousels.py` — 캐러셀 CRUD + `POST /orchestrate` (에이전트 파이프라인 트리거)
- `images.py` — 정적 이미지 서빙 (raw/processed/output)
- `scrape.py` — 수동 스크래핑 트리거 (전체/개별 채널)
- `categories.py` — 채널 카테고리 관리 (admin only)
- `users.py` — 사용자 관리 (admin only)

## 규칙

- 모든 엔드포인트에 `get_current_user` 의존성 필수
- admin 전용: `require_admin()` 데코레이터
- 응답 모델: `app/schemas/` 의 Pydantic 모델 사용
