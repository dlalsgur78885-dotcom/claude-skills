# Agents — AI 오케스트레이션

Plan → Execute → Evaluate 루프로 캐러셀 생성 전 과정을 자동화.

## 파일별 역할

- `base.py` — AgentRole enum (10개), AGENT_LLM_CONFIG, BaseAgent 추상 클래스
- `planner.py` — 사용자 요청 분석 → 실행 계획 생성
- `orchestrator.py` — 메인 실행 루프. 8개 Worker 관리, 의존성 해결, 최대 2회 재시도
- `evaluator.py` — 스텝 결과 검증 및 점수화, 재시도 판단
- `workers.py` — 8개 Worker 구현
- `llm_client.py` — 통합 LLM 클라이언트. CLI-first → LiteLLM fallback
- `prompts/` — 에이전트별 시스템 프롬프트

## 에이전트 목록 (10개)

| 에이전트 | 모델 | 역할 |
|---|---|---|
| planner | Claude Sonnet | 요청 분석 → 실행 계획 |
| evaluator | Sonnet + Gemini (합의) | 결과 검증/재시도 판단 |
| scraper | 없음 (API only) | 인스타그램 데이터 수집 |
| image_processor | 없음 (API only) | 이미지 다운로드/리사이즈/배경 제거 |
| content_generator | Gemini Flash | 슬라이드 텍스트 구조 생성 |
| designer | Gemini Flash | Fabric.js 캔버스 JSON 생성 |
| benchmark_analyst | Claude Sonnet | 인기 포스트 패턴 분석/채널 비교 |
| copywriter | Claude Sonnet | 카피 다듬기/후킹 문구/캡션 생성 |
| image_sourcer | Gemini Flash | 이미지 검색 키워드 생성 + 소싱 |
| publisher | 없음 (API only) | 렌더링 + 인스타그램 발행 |
