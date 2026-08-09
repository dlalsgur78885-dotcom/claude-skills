<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# Frontend — Next.js 웹 대시보드

API base: `http://localhost:8000/api` (환경변수 `NEXT_PUBLIC_API_URL`)

## 구조

- `src/lib/api.ts` — API 클라이언트 (JWT 토큰 관리, 전체 엔드포인트 래핑)
- `src/lib/types.ts` — TypeScript 인터페이스 (User, Channel, Post, Carousel 등)
- `src/lib/store.ts` — Zustand 전역 상태
- `src/components/Sidebar.tsx` — 사이드바 네비게이션
- `src/components/AppShell.tsx` — 레이아웃 쉘
- `src/components/AuthGuard.tsx` — 인증 가드
- `src/components/canvas/` — Fabric.js 캔버스 에디터 컴포넌트

## 페이지

- `/` — 대시보드
- `/posts` — 수집된 소재 (테이블 + 필터)
- `/channels` — 벤치마크 채널 관리
- `/editor/[id]` — 캐러셀 캔버스 에디터
- `/settings` — 설정
- `/login` — 로그인/회원가입
