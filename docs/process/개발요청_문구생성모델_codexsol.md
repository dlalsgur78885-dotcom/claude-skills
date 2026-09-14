# 개발 요청 — 「서버 문구 생성도 codex sol 로」

요청자: solhee 방 (캐러셀기획) · 2026-09-02
상태: **완료 (2026-09-02)** — 아래 「개발 답변」 절 참고

## 뭐가 필요한가

캐러셀 **문구를 짓는 모델을 `codex sol` 로** 바꿔 달라는 것.
사람 지시 — 「모든 캐러셀 문구 후보 생성 codex sol 로 변경해줘」 (2026-09-02).
`codex sol` 은 문구를 짓는 **모델·CLI 이름**이다.

## 봇 쪽은 이미 끝냈다

봇이 대화에서 짓는 문구(1단계 주제 후보 · 3-1 훅 · 3-3 본문 · 5단계 캐프션)는
지침서에 `codex sol` 로 고정해 둔다 → [솔희_캐러셀기획.md](솔희_캐러셀기획.md) 「문구 후보는 codex sol 로 짓는다」 절.

**남은 것은 서버가 짓는 경로다.** 이쪽은 봇이 손대질 수 없다.

## 지금 코드는 이렇게 되어 있다 (2026-09-02 확인)

| 자리 | 내용 |
|---|---|
| 문구 생성 | `backend/app/services/content_gen.py:25-28` — `llm_json(model="gemini-flash", …)` |
| 부르는 곳 | `POST /api/carousels/generate-content` (`backend/app/api/carousels.py:537`) |
| 모델 레지스트리 | `backend/app/agents/llm_client.py:62-79` — **claude(opus·sonnet·haiku) · gemini 뿐이다** |
| CLI 탐지 | 같은 파일 `:27-28` — `shutil.which("claude")` · `shutil.which("gemini")` |

즉 **`codex` 는 provider 로 등록되어 있지 않다.** 지금 상태로는 모델명을 넘겨도 갈 곳이 없다.

## 바꿔 달라는 것

1. **`llm_client.py` 에 codex provider 추가** — `codex` CLI 탐지(`shutil.which`) + 호출 함수.
   claude·gemini 와 같은 모양으로, CLI 없으면 기존 폴백으로 떨어지게.
2. **`MODELS` 에 `codex sol` 키 등록.**
3. **`content_gen.generate_slides` 의 `model="gemini-flash"` 를 그 키로 교체.**

범위는 **문구 생성만**이다. 같은 파일을 쓰는 다른 곳은 건드리지 않아도 된다 —
`bg_vision.py:114`(sonnet, 배경 분석) · `use_post.py:256`(gemini-flash, 소재 분석) · `template_studio.py:617`(gemini-3.1-pro).

## 확인이 필요한 것

- **`codex sol` 의 실제 CLI 호출 형태를 모른다.** (`codex --model sol …` 인지, 프로필인지, 비대화형 출력 플래그가 따로 있는지)
  봇이 확인할 수 없는 부분이라 개발 쪽에서 맞춰 주십시오.
- 문구 생성은 **JSON 으로 받아 파싱**한다(`llm_json`). codex 출력이 JSON 으로 안정적으로 나오는지 확인이 필요하다.
  지금도 파싱에 실패하면 `_fallback_slides` 로 떨어지므로(`content_gen.py:30-34`), 조용히 망가지기 쉽다.

## 그때까지는

봇이 **확정한 문구를 `generate_carousel` 의 `slides` 로 넘긴다.**
그러면 서버가 문구를 새로 지을 일이 없어 **지금도 실제 나가는 문구는 전부 codex sol 이 쓴 것**이다.
이 요청은 대시보드에서 사람이 직접 「캐러셀 만들기」 를 누를 때와, 봇이 `slides` 를 빼먹은 때를 막기 위한 것이다.


---

## 덧붙임 — 프롬프트 캐싱도 함께 (2026-09-02 추가)

사람 지시 — 「모든 캐러셀 작업할 때 캐싱 필수」.
봇이 대화에서 짓는 쪽과 조회 결과 재사용은 지침서에 박았다
(→ [솔희_캐러셀기획.md](솔희_캐러셀기획.md) 「캐싱 — 둘 다 필수다」 절). **서버 쪽이 남았다.**

### 지금 상태 (2026-09-02 확인)

`backend/app/agents/llm_client.py` 에 **프롬프트 캐싱이 없다** — `cache_control` 을 붙이는 곳이 없고,
`_log_usage` 도 input/output 토큰만 기록해 캐시 적중을 볼 수 없다.
캐싱이 도는 것은 번역 결과(`carousels.py:971` `_TRANSLATE_CACHE`) · 외부 이미지 디스크 캐시(`images.py:39` `proxy_cache`) 정도다.

### 바꿔 달라는 것

1. **문구 생성 프롬프트를 「고정 앞부분 + 가변 뒤부분」 으로 나누기** — `content_gen._build_slide_prompt` 기준.
   지금은 주제·톤·장수가 프롬프트 안에 섞여 들어가 **회차마다 앞부분까지 달라진다** — 캐시가 생겨도 못 맞는다.
2. **고정 앞부분에 캐시 표시를 붙인다** — provider 마다 방법이 다르니 codex sol 에서 되는 형태로.
3. **캐시 적중을 로그로 볼 수 있게** — 적중하는지 모르면 동작하는지 확인할 방법이 없다.
   `_log_usage` 에 캐시 읽기/쓰기 토큰 칸을 더하면 좋겠다.

앞의 「바꿔 달라는 것」(codex sol 전환)과 **같은 곳을 건드리는 작업**이라 한 번에 가는 게 난다.

---

## 개발 답변 — 둘 다 반영 완료 (2026-09-02)

### 1. codex sol 전환 — 됐다

| 자리 | 바뀐 것 |
|---|---|
| `llm_client.py` | `CODEX_CLI = shutil.which("codex")` · `_call_codex_cli()` 추가 |
| `llm_client.py` MODELS | **`codex-sol`** 키 등록 (`gpt-5.6-sol`) |
| `content_gen.py:26` | `model="gemini-flash"` → **`model="codex-sol"`** |

**호출 형태** (물어보신 것 — codex-cli 0.147.0 으로 하나씩 확인):

```
codex exec -m gpt-5.6-sol -c model_reasoning_effort="low"       --sandbox read-only --skip-git-repo-check --ephemeral --json       -o <답 파일> -            (프롬프트는 stdin)
```

- `--model sol` 이 아니라 **`-m gpt-5.6-sol`** 이다. 프로필이 아니라 모델 이름이다.
- `exec` 를 빼면 대화 화면이 떠서 서버가 멈춘다.
- 답은 stdout 이 아니라 **`-o` 파일**로 받는다. stdout 에는 진행 로그가 섞인다.
- ⚠ `~/.codex/config.toml` 이 `model_reasoning_effort="xhigh"` 라 그대로 두면 몇 분씩 걸린다.
  호출마다 `low` 로 덮어쓴다(실측 low 16~18초 / medium 22초, 문구 품질 차이 없음).

### 2. JSON 안정성 — 5/5 통과

같은 프롬프트로 5번 돌려 **전부 코드펜스 없는 순수 JSON 배열**로 나왔다.
`_fallback_slides` 로 조용히 떨어지는 일은 없었다. 끝에서 끝까지도 확인 —
「교토 아침 산책 코스」 5장, 「후쿠오카 야타이」 4장 모두 주제가 반영된 실제 문구.

만약을 위해 `--output-schema` 로 형식을 강제하는 길도 있다(codex 가 지원한다).
지금은 필요 없어 넣지 않았다.

### 3. codex 가 없는 서버 대비 — 폴백을 넣었다

`codex-sol` 항목에 `"fallback": "gemini-flash"` 를 달았다. **prod 서버에는 codex CLI 가
없을 가능성이 높은데**, 그때 문구 생성이 통째로 죽는 것보다 예전 모델로 짓는 편이 낫다.
세 경우 모두 시험했다 — CLI 없음 / CLI 가 실패함 / 폴백도 API 키도 없음(제대로 예외).

### 4. 캐싱 — 이미 돌고 있었다. 볼 수만 없었다

- **표시를 붙일 것이 없다.** codex 에는 `cache_control` 같은 게 없고 캐싱이 **자동**이다.
  실측: 아무 설정 없이 입력 28,300 토큰 중 **21,248 이 캐시로 읽혔다(75%)**.
- **프롬프트를 「고정 + 가변」 으로 쪼갤 필요도 없다.** 캐시되는 것은 대부분 codex 자신의
  시스템 프롬프트이고, `_build_slide_prompt` 는 **631 토큰**이라 캐시 최소 단위(1,024)에도
  못 미친다. 쪼개도 얻는 것이 없다.
- **적중을 볼 수 있게 한 것만 했다** — `--json` 이벤트에서 토큰 수를 건져 로그에 남긴다:
  `[LLM/codex] gpt-5.6-sol usage: input=14540 (cached=10624, 73%) output=444`
  `usage_logs` 테이블에는 input/output 칸만 있어 캐시 수치는 로그로만 남는다.
  표에도 쌓으려면 컬럼 추가(마이그레이션)가 필요하니 필요하면 말씀 주십시오.

### 남은 것 — prod 배포

지금 고친 것은 **로컬 코드**다. prod 에 올려야 대시보드 「캐러셀 만들기」에 반영된다.
그리고 prod 에 codex CLI 가 없으면 폴백이 돌아 gemini-flash 로 짓는다 — 그쪽에서도
codex 로 지으려면 **서버에 codex 설치 + 로그인**이 필요하다.
