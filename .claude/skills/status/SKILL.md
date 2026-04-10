---
name: status
description: 프로젝트의 agent 역할, 사용 LLM/API, 코드 라인 수를 한눈에 보여줍니다.
argument-hint: [경로 (선택)]
allowed-tools: Read Bash Glob Grep Agent
---

# 프로젝트 상태 대시보드

`$ARGUMENTS` (없으면 프로젝트 전체)의 현재 상태를 분석하여 보고합니다.

---

## 수집 항목

### 1. Agent 역할 파악

아래 파일들을 탐색하여 정의된 agent를 찾습니다:
- `AGENTS.md` (프로젝트 루트 및 하위 디렉토리)
- `.claude/skills/*/SKILL.md` (등록된 스킬)
- `CLAUDE.md` (프로젝트 설정에 에이전트 관련 내용)

각 agent에 대해:
- 이름/역할
- 책임 범위
- 트리거 조건 (언제 호출되는지)

### 2. LLM / API 사용 현황

코드베이스를 스캔하여 사용 중인 LLM과 API를 찾습니다:

```
검색 패턴:
- openai, anthropic, claude, gemini, codex → LLM SDK/CLI
- HikerAPI, x-access-key → 외부 API
- api_key, API_KEY, OPENAI_API_KEY 등 → API 키 참조
- import anthropic, import openai, from google → SDK import
- codex exec, gemini -p, claude → CLI 호출
- fetch(, axios, httpx, aiohttp → HTTP 클라이언트 (엔드포인트 확인)
```

각 항목에 대해:
- 이름 (Claude, GPT, Gemini 등)
- 사용 방식 (SDK / CLI / API 직접 호출)
- 사용 위치 (파일:라인)
- 모델명 (있으면)

### 3. 코드 라인 수

디렉토리별, 언어별 라인 수를 집계합니다:

```bash
# 언어별 파일 확장자
# Python: .py
# TypeScript/JavaScript: .ts, .tsx, .js, .jsx
# CSS: .css, .scss
# HTML: .html
# Config: .json, .yaml, .yml, .toml
# Markdown: .md

# 제외 대상
# node_modules, .next, __pycache__, .git, dist, build, .venv, venv
```

집계 방법:
- `wc -l`로 파일별 라인 수
- 빈 줄과 주석 줄 포함 (전체 라인)
- 디렉토리별 소계 + 언어별 소계 + 전체 합계

---

## 출력 형식

```
═══ 프로젝트 상태 ═══

## Agents
| Agent | 역할 | 트리거 |
|-------|------|--------|
| ... | ... | ... |

## LLM / API
| 이름 | 방식 | 모델 | 위치 |
|------|------|------|------|
| ... | ... | ... | ... |

## 코드 라인 수
| 디렉토리 | .py | .ts/.tsx | .css | 기타 | 합계 |
|----------|-----|---------|------|------|------|
| backend/ | ... | - | - | ... | ... |
| frontend/| - | ... | ... | ... | ... |
| 합계 | ... | ... | ... | ... | ... |

총 라인: N줄 (코드 N개 파일)
```

---

## 실행 규칙

- 파일 내용은 읽되 **수정하지 않습니다** (읽기 전용).
- node_modules, .next, __pycache__, .git 등은 반드시 제외합니다.
- LLM/API 검색 시 .env 파일의 키 값은 출력하지 않습니다 (키 이름만 표시).
- 결과가 길면 요약 테이블만 보여주고, 상세는 접어둡니다.
