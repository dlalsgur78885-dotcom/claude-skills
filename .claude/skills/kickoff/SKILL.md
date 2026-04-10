---
name: kickoff
description: 프로젝트 시작 시 agent 오케스트레이션 구조를 설계하고, 필요한 agent/skill을 GitHub에서 탐색합니다.
argument-hint: [프로젝트 설명 또는 목표]
allowed-tools: Read Bash WebSearch WebFetch Agent Glob Grep
---

# 프로젝트 킥오프: Agent 오케스트레이션 설계

`$ARGUMENTS` 프로젝트에 맞는 멀티 에이전트 구조를 설계합니다.

## 1단계: 프로젝트 분석

프로젝트 디렉토리를 탐색하여 현재 상태를 파악합니다:
- CLAUDE.md, AGENTS.md 존재 여부
- 기존 코드 구조, 기술 스택
- 프로젝트 규모와 복잡도

## 2단계: 오케스트레이션 구조 제안

프로젝트 특성에 맞는 agent 역할을 설계합니다. 아래 역할 중 필요한 것만 선별합니다:

### 핵심 역할

| 역할 | 책임 | 언제 필요한가 |
|---|---|---|
| **Planner** | 요구사항 분석, 작업 분해, 우선순위 결정 | 모든 프로젝트 |
| **Executor** | 실제 코드 구현 | 모든 프로젝트 |
| **Reviewer** | 코드 리뷰, 버그/보안 체크, 품질 검증 | 중규모 이상 |
| **Evaluator** | 결과물 평가, 테스트, 성능 측정 | 품질이 중요한 프로젝트 |
| **Researcher** | 기술 조사, API 문서 분석, 벤치마킹 | 새로운 기술 도입 시 |
| **Designer** | UI/UX 설계, 디자인 시스템 구축 | 프론트엔드 포함 프로젝트 |
| **DevOps** | CI/CD, 배포, 인프라 설정 | 배포가 필요한 프로젝트 |
| **Writer** | 문서화, API 스펙, README | 팀/오픈소스 프로젝트 |

### 오케스트레이션 패턴

프로젝트 규모에 따라 패턴을 추천합니다:

- **소규모** (1-2명, 단일 기능): Planner + Executor 2인 구조
- **중규모** (팀 프로젝트, 여러 모듈): Planner → Executor + Reviewer 3인 구조
- **대규모** (복잡한 시스템): 전체 역할 + Leader 오케스트레이터

## 3단계: GitHub에서 agent/skill 탐색

설계한 구조에 필요한 agent와 skill을 GitHub에서 검색합니다.

### 탐색 대상 레포지토리

아래 레포들을 우선 탐색합니다:

1. **anthropics/skills** — Anthropic 공식 스킬
2. **wshobson/agents** — 182개 agent, 149개 skill 모음
3. **hesreallyhim/awesome-claude-code** — 큐레이션된 스킬/플러그인 목록
4. **travisvn/awesome-claude-skills** — 큐레이션된 Claude 스킬 리소스
5. **jeremylongshore/claude-code-plugins-plus-skills** — 340 플러그인 + 1367 스킬

### 탐색 방법

```bash
# 관련 agent/skill 검색
gh search repos "<역할명> claude skill" --sort stars --limit 5
```

프로젝트에 맞는 agent와 skill을 찾아서 추천하고, 설치 방법을 안내합니다.

## 4단계: AGENTS.md 생성

탐색 결과를 종합하여 프로젝트 루트에 `AGENTS.md` 파일을 생성합니다.

### 출력 형식

```markdown
# Agent 오케스트레이션

## 구조
[오케스트레이션 패턴 다이어그램 - 텍스트]

## Agents

### Planner
- 역할: ...
- 트리거: 새 기능 요청, 리팩토링 계획
- 참조 skill: ...

### Executor
- 역할: ...
- 트리거: 구현 작업
- 참조 skill: ...

(이하 역할별 동일 구조)

## 추천 Skill
| 스킬 | 출처 | 용도 |
|---|---|---|
| ... | GitHub URL | ... |

## 워크플로우
1. 요청 → Planner가 작업 분해
2. Executor가 구현
3. Reviewer가 검증
4. Evaluator가 최종 평가
```

## 핵심 원칙

- 프로젝트에 **실제로 필요한 역할만** 제안합니다. 과도한 구조는 오버헤드입니다.
- 각 agent의 책임 범위를 명확히 분리합니다.
- GitHub 탐색 결과는 stars 수, 최근 업데이트, 실제 유용성을 기준으로 필터링합니다.
- 추천 skill은 바로 설치 가능한 것 위주로 안내합니다.
