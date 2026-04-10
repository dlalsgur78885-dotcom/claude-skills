---
name: kickoff
description: 프로젝트 시작 시 브레인스토밍 → Q&A → agent 오케스트레이션 설계 → GitHub 스킬 탐색 → 산출물 생성까지 풀 킥오프를 수행합니다.
argument-hint: [프로젝트 설명 또는 목표]
allowed-tools: Read Bash WebSearch WebFetch Agent Glob Grep AskUserQuestion
---

# 프로젝트 킥오프: Agent 오케스트레이션 설계

`$ARGUMENTS` 프로젝트에 맞는 멀티 에이전트 구조를 설계합니다.

---

## Phase 0: 브레인스토밍 (superpowers 참고)

먼저 프로젝트 아이디어를 넓게 탐색합니다.

1. 사용자가 제시한 목표를 기반으로 **3가지 접근 방식**을 제안합니다:
   - 최소 기능 (MVP) 접근
   - 균형잡힌 접근 (추천)
   - 풀스펙 접근
2. 각 접근별로 예상되는 **핵심 모듈**, **기술 스택**, **에이전트 필요 수**를 간략히 나열합니다.
3. 사용자에게 방향을 선택하도록 질문합니다.

> 이 단계에서 AskUserQuestion으로 사용자의 선택을 받습니다.

---

## Phase 1: 인터랙티브 Q&A (conductor 참고)

프로젝트 맥락을 파악하기 위해 **순차적으로 질문**합니다. 각 질문에 2-3개 추천 답변을 제시합니다.

### 질문 흐름

```
Q1. 프로젝트 유형은?
   → [a] 새 프로젝트 (Greenfield)
   → [b] 기존 프로젝트 개선 (Brownfield)
   → [c] 마이그레이션/리팩토링

Q2. 규모는?
   → [a] 소규모 (1인, 단일 기능)
   → [b] 중규모 (2-5인, 여러 모듈)
   → [c] 대규모 (복잡한 시스템, 마이크로서비스)

Q3. 프론트엔드가 있나요?
   → [a] 없음 (API/CLI만)
   → [b] 웹 (React/Next/Vue 등)
   → [c] 모바일 (React Native/Flutter 등)
   → [d] 둘 다

Q4. 배포 환경은?
   → [a] 아직 미정
   → [b] 클라우드 (AWS/GCP/Vercel 등)
   → [c] 셀프호스팅
   → [d] 배포 불필요 (로컬/CLI)

Q5. 가장 중요한 가치는?
   → [a] 빠른 출시 (속도 우선)
   → [b] 코드 품질 (안정성 우선)
   → [c] 확장성 (미래 대비)
```

> 기존에 CLAUDE.md, package.json, requirements.txt 등이 있으면 자동 감지하여 답변을 미리 채웁니다.
> 한 번에 묶어서 질문해도 됩니다. 컨텍스트에서 유추 가능한 항목은 건너뜁니다.

---

## Phase 2: 프로젝트 분석

### 자동 탐색

프로젝트 디렉토리를 스캔합니다:

- CLAUDE.md, AGENTS.md 존재 여부
- 기존 코드 구조, 기술 스택 (package.json, requirements.txt, go.mod 등)
- 디렉토리 깊이와 파일 수 → 규모 추정
- 기존 테스트 존재 여부
- CI/CD 설정 존재 여부

### 분석 결과 요약

```
📊 프로젝트 현황
- 유형: Greenfield / Brownfield
- 스택: Python + FastAPI / Next.js + TypeScript / ...
- 규모: 파일 N개, 디렉토리 N개
- 테스트: 있음(pytest) / 없음
- CI/CD: 있음(GitHub Actions) / 없음
- 기존 에이전트 설정: 있음 / 없음
```

---

## Phase 3: 오케스트레이션 구조 설계

Phase 0-2 결과를 종합하여 agent 구조를 설계합니다.

### 역할 풀

| 역할 | 책임 | 선정 조건 |
|---|---|---|
| **Planner** | 요구사항 분석, 작업 분해, 우선순위 | 모든 프로젝트 |
| **Executor** | 코드 구현 | 모든 프로젝트 |
| **Reviewer** | 코드 리뷰, 버그/보안 체크, 품질 검증 | 중규모 이상 or 품질 우선 |
| **Evaluator** | 테스트 설계/실행, 성능 측정, 결과 판정 | 품질 우선 프로젝트 |
| **Researcher** | 기술 조사, API 문서 분석, 벤치마킹 | 새로운 기술 도입 |
| **Designer** | UI/UX 설계, 디자인 시스템, 컴포넌트 구조 | 프론트엔드 포함 |
| **DevOps** | CI/CD, 배포, 인프라, 모니터링 | 배포 필요 |
| **Writer** | 문서화, API 스펙, README, CHANGELOG | 팀/오픈소스 |
| **Security** | 보안 감사, 취약점 스캔, 인증/인가 설계 | 민감한 데이터 처리 |

### 오케스트레이션 패턴

Q&A 결과에 따라 자동 선택:

**패턴 A: Solo** (소규모 + 속도 우선)
```
User → Planner/Executor (1인 다역)
```

**패턴 B: Trio** (중규모 or 품질 우선)
```
User → Planner → Executor → Reviewer
                          ↘ Evaluator (테스트)
```

**패턴 C: Squad** (대규모 or 풀스펙)
```
User → Planner (리드)
         ├→ Researcher (조사)
         ├→ Designer (설계)
         ├→ Executor (구현) → Reviewer (검증)
         ├→ DevOps (배포)
         └→ Evaluator (최종 판정)
```

> 패턴과 역할 선정 이유를 사용자에게 설명하고 확인을 받습니다.

---

## Phase 4: GitHub에서 agent/skill 탐색

설계한 구조의 각 역할에 맞는 agent/skill을 GitHub에서 검색합니다.

### 1차: 큐레이션된 레포 우선 탐색

| 레포 | 내용 | 탐색 방법 |
|---|---|---|
| [anthropics/skills](https://github.com/anthropics/skills) | 공식 스킬 | README + skills/ 디렉토리 |
| [wshobson/agents](https://github.com/wshobson/agents) | 182 agent, 149 skill | plugins/ 디렉토리에서 역할별 검색 |
| [obra/superpowers](https://github.com/obra/superpowers) | 14개 고품질 스킬 | skills/ 디렉토리 |
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | 큐레이션 목록 | README에서 카테고리별 |
| [travisvn/awesome-claude-skills](https://github.com/travisvn/awesome-claude-skills) | 스킬 리소스 | README |
| [avifenesh/agentsys](https://github.com/avifenesh/agentsys) | 47 agent, 40 skill | agents/, skills/ 디렉토리 |

### 2차: 키워드 검색

```bash
gh search repos "<역할명> claude skill" --sort stars --limit 5
gh search repos "<기술스택> claude agent" --sort stars --limit 5
```

### 필터링 기준

- Stars 10+ (최소 검증)
- 최근 6개월 내 업데이트
- SKILL.md 또는 AGENTS.md 형식 준수
- 실제 설치/사용 가능 여부

### 추천 형식

각 추천 스킬에 대해:
```
✅ <스킬명> (★ stars)
   출처: <GitHub URL>
   용도: <한 줄 설명>
   설치: <복사 명령어 or 심링크>
   적합도: ★★★★☆ (역할과의 매칭도)
```

---

## Phase 5: 산출물 생성

### 5-1. AGENTS.md 생성

프로젝트 루트에 생성합니다:

```markdown
# Agent 오케스트레이션

## 패턴: [Solo / Trio / Squad]

## 구조도
[텍스트 다이어그램]

## Agents

### [역할명]
- **책임**: ...
- **트리거**: 어떤 상황에서 이 agent를 호출하는지
- **입력**: 무엇을 받는지
- **출력**: 무엇을 산출하는지
- **참조 skill**: GitHub에서 찾은 관련 스킬
- **제약**: 이 agent가 하지 않는 것

(역할별 반복)

## 워크플로우
1. ...
2. ...

## 추천 Skills
| 스킬 | 출처 | 역할 | 설치 |
|---|---|---|---|
| ... | URL | ... | ... |
```

### 5-2. GitHub Issues 생성 (ccpm 참고, 선택사항)

사용자에게 물어본 후, 원하면 초기 작업을 GitHub Issues로 생성합니다:

```bash
gh issue create --title "[Phase] 작업 제목" --body "설명" --label "kickoff"
```

생성할 이슈 목록:
- 각 agent 역할별 설정 이슈
- 추천 skill 설치 이슈
- 초기 구현 마일스톤 이슈

> 이슈 생성 전 반드시 사용자 확인을 받습니다.

### 5-3. 킥오프 요약

마지막에 한눈에 볼 수 있는 요약을 출력합니다:

```
🚀 킥오프 완료

프로젝트: <이름>
패턴: <Solo/Trio/Squad>
Agent 수: N개
추천 Skill: N개

생성된 파일:
  ✅ AGENTS.md

다음 단계:
  1. 추천 skill 설치: ...
  2. 첫 번째 작업: ...
  3. ...
```

---

## 핵심 원칙

- **실제로 필요한 역할만** 제안합니다. 과도한 구조는 오버헤드입니다.
- **사용자의 선택을 존중**합니다. 추천은 하되 강요하지 않습니다.
- 유추 가능한 질문은 **건너뛰고**, 핵심만 묻습니다.
- GitHub 탐색은 **stars + 최근 업데이트 + 실사용 가능** 기준으로 필터링합니다.
- 모든 비가역적 액션(이슈 생성, 파일 덮어쓰기)은 **사전 확인**합니다.
