---
name: swarm
description: Evaluator(Codex+Gemini+Claude) → Planner → Worker 멀티 에이전트 파이프라인. 3개 AI가 문제를 찾고, 계획을 세우고, 병렬로 실행합니다.
argument-hint: [작업 지시 또는 코드 경로]
allowed-tools: Read Bash Agent Glob Grep AskUserQuestion Write Edit
---

# Swarm: 멀티 AI 에이전트 파이프라인

`$ARGUMENTS`에 대해 3단계 멀티 에이전트 파이프라인을 실행합니다.

---

## 아키텍처

```
┌─────────────── Evaluator (문제 발견) ───────────────┐
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Codex CLI│  │Gemini CLI│  │ Claude Opus      │   │
│  │ (review) │  │ (-p)     │  │ (Agent tool)     │   │
│  └────┬─────┘  └────┬─────┘  └────────┬─────────┘   │
│       │              │                 │             │
│       └──────────────┼─────────────────┘             │
│                      ▼                               │
│            투표 & 종합 (3개 AI 의견 교차 검증)         │
└──────────────────────┬───────────────────────────────┘
                       ▼
┌─────────────── Planner (계획 수립) ──────────────────┐
│  - 발견된 문제를 우선순위별로 정렬                      │
│  - 각 문제를 독립적 작업 단위로 분해                    │
│  - 작업 간 의존성 파악                                │
│  - Worker에게 할당할 작업 목록 생성                     │
└──────────────────────┬───────────────────────────────┘
                       ▼
┌─────────────── Workers (병렬 실행) ──────────────────┐
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │Worker 1 │ │Worker 2 │ │Worker 3 │ │Worker N │   │
│  │(Agent)  │ │(Agent)  │ │(Agent)  │ │(Agent)  │   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
└──────────────────────────────────────────────────────┘
```

---

## Phase 1: Evaluator — 문제 발견

3개 AI에게 **동일한 프롬프트**로 분석을 요청하고 결과를 교차 검증합니다.

### 1-1. 분석 대상 파악

먼저 `$ARGUMENTS`를 분석하여 대상을 파악합니다:
- 파일/디렉토리 경로가 주어졌으면 해당 코드를 읽음
- 작업 지시만 있으면 관련 코드를 프로젝트에서 탐색

분석 대상 코드를 수집하여 하나의 컨텍스트로 정리합니다.

### 1-2. 3개 AI 동시 실행

아래 3개를 **병렬로** 실행합니다:

**Codex CLI** (코드 리뷰 특화):
```bash
codex exec -p "아래 코드를 분석해서 문제점, 버그, 개선사항을 찾아줘. 각 항목을 [심각도: critical/major/minor] [카테고리: bug/security/performance/style/architecture] 형식으로 정리해줘. 파일 경로와 라인 번호를 포함해줘.

대상 코드:
<코드 내용>" --writable=false
```

**Gemini CLI** (넓은 시야 분석):
```bash
gemini -p "아래 코드를 분석해서 문제점, 버그, 개선사항을 찾아줘. 각 항목을 [심각도: critical/major/minor] [카테고리: bug/security/performance/style/architecture] 형식으로 정리해줘. 파일 경로와 라인 번호를 포함해줘.

대상 코드:
<코드 내용>"
```

**Claude Opus** (Agent tool 활용):
```
Agent tool로 서브에이전트를 생성하여 동일한 프롬프트로 분석.
Agent는 직접 파일을 읽고 Grep/Glob으로 관련 코드를 추가 탐색할 수 있음.
```

### 1-3. 결과 종합 — 투표 시스템

3개 AI의 결과를 비교하여 종합합니다:

| 신뢰도 | 조건 | 표시 |
|---|---|---|
| **확정** | 3/3 AI가 동일 문제 지적 | 🔴 |
| **높음** | 2/3 AI가 지적 | 🟡 |
| **참고** | 1/3 AI만 지적 | 🔵 |

종합 시 규칙:
- 동일한 문제를 다른 표현으로 지적한 경우 → 하나로 병합
- 서로 모순되는 의견 → 양쪽 근거를 병기
- critical 이슈는 1개 AI만 지적해도 🟡 이상으로 승격

### 1-4. Evaluator 결과 출력

```
═══ Evaluator 결과 ═══

🔴 확정 (3/3 일치): N건
🟡 높음 (2/3 일치): N건
🔵 참고 (1/3 지적): N건

[#1] 🔴 critical/bug — SQL 인젝션 취약점
  파일: app/api/users.py:42
  Codex: "직접 문자열 포맷팅으로 쿼리 생성"
  Gemini: "파라미터 바인딩 없이 user input 사용"
  Claude: "SQLAlchemy text() 사용 시 바인드 파라미터 누락"

[#2] 🟡 major/performance — N+1 쿼리
  파일: app/api/posts.py:78
  Codex: (미지적)
  Gemini: "루프 내 개별 쿼리 실행"
  Claude: "joinedload/selectinload 없이 관계 접근"

...
```

> 결과를 사용자에게 보여주고 진행 여부를 확인합니다.

---

## Phase 2: Planner — 계획 수립

Evaluator 결과를 기반으로 실행 계획을 세웁니다.

### 2-1. 우선순위 정렬

```
1순위: 🔴 critical (보안, 데이터 손실)
2순위: 🔴 major (기능 버그)
3순위: 🟡 major (성능, 아키텍처)
4순위: 🟡 minor + 🔵 (스타일, 개선)
```

### 2-2. 작업 분해

각 문제를 독립적인 작업 단위로 분해합니다:

```
Task 1: [파일: path] [유형: fix/refactor/add]
  - 변경 내용: ...
  - 영향 범위: ...
  - 의존성: 없음 / Task N 이후

Task 2: ...
```

### 2-3. 의존성 분석 & 실행 순서

```
Wave 1 (병렬 가능): Task 1, Task 3, Task 5
Wave 2 (Wave 1 완료 후): Task 2, Task 4
Wave 3: Task 6
```

### 2-4. 계획 확인

전체 계획을 사용자에게 보여주고:
- 스킵할 작업이 있는지
- 순서를 변경할 것이 있는지
- 추가할 작업이 있는지

확인을 받습니다.

---

## Phase 3: Workers — 병렬 실행

### 3-1. Wave별 병렬 실행

각 Wave의 Task들을 **Agent tool로 병렬 서브에이전트**를 생성하여 실행합니다.

각 Worker에게 전달하는 프롬프트:
```
당신은 Worker agent입니다.

## 작업
<Task 내용>

## 컨텍스트
- Evaluator가 발견한 문제: <해당 문제 상세>
- 3개 AI의 분석 의견: <Codex/Gemini/Claude 의견>
- 관련 파일: <파일 경로>

## 규칙
- 이 Task의 범위만 수정하세요. 다른 파일은 건드리지 마세요.
- 변경 전후 테스트가 있으면 실행하여 검증하세요.
- 완료 후 변경 내용을 요약해주세요.
```

### 3-2. Wave 실행 흐름

```
Wave 1 시작
  ├→ Worker 1 (Agent, 병렬)
  ├→ Worker 2 (Agent, 병렬)
  └→ Worker 3 (Agent, 병렬)
  ... 모든 Worker 완료 대기 ...

Wave 2 시작 (Wave 1 결과 반영)
  ├→ Worker 4 (Agent, 병렬)
  └→ Worker 5 (Agent, 병렬)
  ... 완료 대기 ...
```

### 3-3. 충돌 방지

- 같은 파일을 여러 Worker가 수정하는 경우 → 같은 Wave에 넣지 않음
- 불가피하면 수정 영역(라인 범위)이 겹치지 않도록 분리

---

## Phase 4: 검증 & 보고

### 4-1. 자동 검증

모든 Worker 완료 후:
1. 기존 테스트 실행 (`pytest`, `npm test` 등)
2. 린트 실행 (있으면)
3. 타입 체크 실행 (있으면)

### 4-2. 최종 보고

```
═══ Swarm 실행 완료 ═══

Evaluator: 문제 N건 발견 (Codex + Gemini + Claude)
Planner:   Task N건 / Wave N개
Workers:   N건 완료 / N건 실패

변경된 파일:
  ✅ app/api/users.py — SQL 인젝션 수정
  ✅ app/api/posts.py — N+1 쿼리 해결
  ❌ app/utils/cache.py — 테스트 실패 (롤백됨)

테스트: ✅ 통과 (N/N)
```

### 4-3. 실패 처리

Worker가 실패하거나 테스트가 깨진 경우:
- 해당 변경만 git stash로 분리
- 사용자에게 수동 처리할지 재시도할지 질문

---

## 설정 옵션

사용자가 인자로 동작을 제어할 수 있습니다:

```
/swarm backend/app              ← 특정 경로 분석
/swarm "인증 로직 점검해줘"      ← 자연어 지시
/swarm --eval-only backend/     ← Evaluator만 실행 (수정 안 함)
/swarm --skip-codex             ← Codex 제외
/swarm --skip-gemini            ← Gemini 제외
```

플래그 파싱: `$ARGUMENTS`에서 `--`로 시작하는 토큰을 플래그로, 나머지를 작업 대상으로 분리합니다.

---

## 핵심 원칙

- **Evaluator는 읽기만**, 코드를 수정하지 않습니다.
- **Planner는 사용자 확인 후** Worker를 시작합니다.
- **Worker는 할당된 범위만** 수정합니다.
- 모든 단계에서 사용자가 **중단/스킵/수정** 가능합니다.
- Codex/Gemini CLI 실행 실패 시 나머지 AI로 계속 진행합니다 (graceful degradation).
