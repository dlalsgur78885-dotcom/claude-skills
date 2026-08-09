# CLI — 커맨드라인 인터페이스

Typer 기반. 웹 서버 없이 단독 실행 가능.

## 명령어

- `serve` — FastAPI 서버 시작 (--host, --port, --reload)
- `scrape` — 인스타그램 수집 (--channel/-c, --limit/-l)
- `process` — 이미지 처리 (--post/-p)
- `generate` — AI 캐러셀 생성 (--topic/-t, --source/-s, --template)
- `scheduler` — 정기 스크래핑 데몬 (start/stop)
- `channels list` — 채널 목록 조회
- `channels add` — 채널 추가 (--name, --category, --tags)
