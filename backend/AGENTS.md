# Backend

FastAPI 비동기 백엔드. SQLAlchemy 2.0 async + aiosqlite.

## 폴더 구조

- `app/agents/` — AI 에이전트 오케스트레이션 (Planner → Workers → Evaluator)
- `app/api/` — REST API 엔드포인트 (`/api` prefix)
- `app/models/` — SQLAlchemy ORM 모델
- `app/schemas/` — Pydantic 요청/응답 스키마
- `app/services/` — 비즈니스 로직 (스크래핑, 이미지 처리, 콘텐츠 생성, 디자인)
- `app/templates/` — Fabric.js 캔버스 디자인 템플릿 JSON
- `cli/` — Typer CLI (서버 없이 단독 실행)

## 규칙

- DB URL: `sqlite+aiosqlite:///./data/db.sqlite3`
- 설정: `app/config.py` (pydantic-settings, `.env` 파일 로드)
- 라우터 등록: `app/api/router.py`에서 통합
- 모든 API는 `get_current_user` 의존성으로 인증 필수
- admin 전용 작업: `require_admin()` 데코레이터 사용
