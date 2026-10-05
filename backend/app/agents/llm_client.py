"""Unified LLM client — CLI-first, API-fallback.

Calls `claude` and `gemini` CLI tools directly when available,
falling back to LiteLLM API only when CLI is unavailable or an API key is set.

CLI tools used:
  claude -p "prompt" --output-format text   (Claude Code CLI)
  gemini -p "prompt"                        (Google Gemini CLI)
  codex exec -m gpt-6-sol -o out.txt -      (OpenAI Codex CLI — 문구 생성)

Environment variables (only needed if CLI unavailable):
  ANTHROPIC_API_KEY  - for Claude models via API
  GEMINI_API_KEY     - for Gemini models via API
"""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
import tempfile
from typing import Any

logger = logging.getLogger(__name__)

# ─── CLI Detection ───

CLAUDE_CLI = shutil.which("claude")
GEMINI_CLI = shutil.which("gemini")
CODEX_CLI = shutil.which("codex")

# 사람이 쓰는 ~/.codex/config.toml 은 model_reasoning_effort="xhigh" 다 — 코딩용 설정이라
# 문구 한 벌에 몇 분이 걸린다. 서버 문구 생성은 짧은 JSON 한 덩어리라 낮은 추론으로 충분하다
# (2026-09-02 실측: low 16~18초 / medium 22초, 결과 품질 차이 없음). 호출마다 덮어쓴다.
CODEX_REASONING_EFFORT = "low"

# 문구 짓기에는 codex 의 코딩 에이전트 지침과 도구(브라우저·셸·이미지·앱 …)가 필요 없다.
# 그대로 두면 「OK」 한 마디에도 입력이 1.39만 토큰이었다 — 지침을 아래 짧은 것으로 바꾸고
# 도구 기능을 끄면 0.7만이 된다(2026-10-05 실측, 번역 결과 같음). 호출이 회차당 90번 안팎이다.
# 이미지 생성(`services/codex_image.py`)은 따로 codex 를 부르므로 여기와 상관없다.
CODEX_INSTRUCTIONS_FILE = Path(__file__).with_name("codex_writer_instructions.md")
CODEX_OFF_FEATURES = (
    "apps", "browser_use", "browser_use_external", "computer_use", "image_generation",
    "multi_agent", "plugins", "skill_search", "tool_suggest", "goals", "sleep_tool",
    "in_app_browser", "realtime_conversation", "shell_tool", "unified_exec", "hooks", "mentions_v2",
)


def _codex_lean_flags() -> list[str]:
    flags: list[str] = []
    if CODEX_INSTRUCTIONS_FILE.exists():
        flags += ["-c", f'model_instructions_file="{CODEX_INSTRUCTIONS_FILE.as_posix()}"']
    for feature in CODEX_OFF_FEATURES:
        flags += ["-c", f"features.{feature}=false"]
    return flags

# Running totals for vision token usage (process-local; reset by tests).
# Authoritative source is the `usage_logs` DB table written by _log_usage();
# this dict is kept only for the cheap `_USAGE_TOTALS["calls"]` summary that
# existing call sites read. Don't add new readers — query the DB instead.
_USAGE_TOTALS: dict[str, int] = {"input": 0, "output": 0, "calls": 0}


async def _log_usage(model: str, input_tokens: int, output_tokens: int, call_type: str = "text") -> None:
    """Insert a row into usage_logs. Never raises — logging failure must not
    break the LLM call. Imports happen inside to keep the LLM module importable
    in contexts where the DB isn't set up (CLI scripts, tests)."""
    try:
        from app.database import async_session
        from app.models.usage_log import UsageLog
        async with async_session() as session:
            session.add(UsageLog(
                model=model,
                call_type=call_type,
                input_tokens=int(input_tokens or 0),
                output_tokens=int(output_tokens or 0),
            ))
            await session.commit()
    except Exception as e:
        logger.debug(f"[usage] failed to persist usage row: {e}")

logger.info(f"[LLM] claude CLI: {CLAUDE_CLI or 'not found'}")
logger.info(f"[LLM] gemini CLI: {GEMINI_CLI or 'not found'}")
logger.info(f"[LLM] codex CLI: {CODEX_CLI or 'not found'}")


# ─── Model Registry ───
# Format: "short_name" → {"provider": "claude"|"gemini", "model_id": "...", "cli_flag": "..."}

MODELS = {
    # Claude (CLI or Anthropic API)
    "opus":    {"provider": "claude", "model_id": "claude-opus-4-6",         "cli_model": "opus"},
    "sonnet":  {"provider": "claude", "model_id": "claude-sonnet-4-6",       "cli_model": "sonnet"},
    "haiku":   {"provider": "claude", "model_id": "claude-haiku-4-5-20251001", "cli_model": "haiku"},

    # Gemini (CLI or Google API)
    "gemini-flash":          {"provider": "gemini", "model_id": "gemini/gemini-2.5-flash",                "cli_model": "gemini-2.5-flash"},
    "gemini-flash-thinking": {"provider": "gemini", "model_id": "gemini/gemini-2.5-flash",                "cli_model": "gemini-2.5-flash"},
    "gemini-pro":            {"provider": "gemini", "model_id": "gemini/gemini-2.5-pro",                  "cli_model": "gemini-2.5-pro"},
    "gemini-3.1-pro":        {"provider": "gemini", "model_id": "gemini/gemini-3.1-pro-preview",         "cli_model": "gemini-3.1-pro-preview"},
    # Vision-capable Flash Lite variant for extraction tasks where Pro accuracy is unnecessary.
    # Use for content extraction on benchmark slides where we don't need Pro accuracy.
    "gemini-flash-lite":     {"provider": "gemini", "model_id": "gemini/gemini-2.5-flash-lite",          "cli_model": "gemini-2.5-flash-lite"},

    # Codex (CLI 전용 — API 경로가 없다). 캐러셀 문구 생성용.
    # CLI 가 없거나 실패하면 "fallback" 모델로 넘어간다 — prod 서버에는 codex 가 없을 수 있고,
    # 그때 문구 생성이 통째로 죽는 것보다 예전 모델로 짓는 편이 낫다.
    # 2026-09-23 gpt-5.6-sol → gpt-6-sol. 같은 주제로 나란히 돌려 고른 것이다:
    # 훅 37초→10초 · 본문 12초→8초로 **2.3배 빠르고**, 규칙(두 줄 훅·A/B/C·결 분리)은
    # 그대로 지킨다. 결은 5.6 쪽이 점잖고 6 쪽이 구어에 가깝다.
    # ⚠ 2026-09-28 폴백을 gemini-flash → sonnet 으로 바꿨다. gemini CLI 가 계정 문제로 죽는다
    #   (IneligibleTierError — 「Gemini Code Assist for individuals 를 더는 지원하지 않는다」).
    #   그날 codex 사용량 한도에 걸렸을 때 폴백도 같이 죽어 **문구 생성이 통째로 멈췄다.**
    "codex-sol": {"provider": "codex", "model_id": "gpt-6-sol", "cli_model": "gpt-6-sol",
                  "fallback": "sonnet"},
    # 가벼운 자리 전용(번역·여는 한 줄). 더 빠르지만 **문구를 짓게 하지 않는다** —
    # 같은 시험에서 원문에 없는 「창가석」을 지어냈고 「モンスター」를 「괴물」로 옮겼다.
    "codex-luna": {"provider": "codex", "model_id": "gpt-6-luna", "cli_model": "gpt-6-luna",
                   "fallback": "sonnet"},

    # Image generation/edit (a.k.a. nanobanana, nanobanana2)
    "nanobanana2":           {"provider": "gemini", "model_id": "gemini-3.1-flash-image-preview",       "cli_model": ""},  # Flash, fast/cheap
    "nanobanana-pro":        {"provider": "gemini", "model_id": "gemini-3-pro-image-preview",            "cli_model": ""},  # Pro, slower/higher fidelity
}


def resolve_model(name: str) -> str:
    """Resolve short name to full model ID (for display/logging)."""
    entry = MODELS.get(name)
    if entry:
        return entry["model_id"]
    return name


def _has_api_key(provider: str) -> bool:
    if provider == "claude":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    if provider == "gemini":
        return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    return False


def _can_use_cli(provider: str) -> bool:
    if provider == "claude":
        return bool(CLAUDE_CLI)
    if provider == "gemini":
        return bool(GEMINI_CLI)
    if provider == "codex":
        return bool(CODEX_CLI)
    return False


# ─── CLI Backends ───

async def _call_claude_cli(
    prompt: str,
    system: str | None = None,
    model: str = "sonnet",
    max_tokens: int = 4096,
) -> str:
    """Call Claude via `claude` CLI (Claude Code)."""
    # Write prompt to temp file to avoid shell escaping issues
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        cmd = [
            CLAUDE_CLI, "-p",
            "--model", model,
            "--output-format", "text",
            "--max-turns", "1",
        ]
        if system:
            cmd.extend(["--system-prompt", system])

        # Pipe prompt from file
        with open(prompt_file, "r", encoding="utf-8") as pf:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=pf,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # 지침서를 통째로 싣는 자리(캐러셀 문구)는 프롬프트가 2만 자를 넘는다 —
            # 120초로는 모자라 codex 폴백이 그대로 시간 초과로 죽었다(2026-09-28).
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"claude CLI error (exit {proc.returncode}): {err}")

        return stdout.decode("utf-8", errors="replace").strip()
    finally:
        try:
            os.unlink(prompt_file)
        except OSError:
            # ⚠ 윈도우에서는 CLI 가 아직 파일을 물고 있으면 지워지지 않는다(WinError 32).
            #   임시 파일 하나 남는 것보다, 답을 다 받아 놓고 **여기서 터지는 쪽**이 훨씬 나쁘다
            #   (2026-09-28 — 주제 생성이 답을 받고도 이 줄에서 죽었다).
            pass


async def _call_gemini_cli(
    prompt: str,
    system: str | None = None,
    model: str = "gemini-2.5-flash",
) -> str:
    """Call Gemini via `gemini` CLI.

    ⚠ 2026-09-28 이 길은 **이 기계에서 안 돈다.** 두 가지가 겹쳐 있다:
      ① `-p` 뒤에 값을 안 주고 프롬프트를 stdin 으로 넣는데, 지금 CLI 는 값을 요구한다
         (`Not enough arguments following: p`).
      ② 고쳐도 로그인 자체가 막힌다 — `IneligibleTierError`(개인용 Gemini Code Assist 지원 종료).
    그래서 codex 폴백을 claude 쪽(sonnet)으로 돌렸다. 여기는 계정이 풀리면 다시 본다.
    """
    # Combine system + user prompt for CLI
    full_prompt = prompt
    if system:
        full_prompt = f"[System Instructions]\n{system}\n\n[User Request]\n{prompt}"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(full_prompt)
        prompt_file = f.name

    try:
        cmd = [GEMINI_CLI, "-p"]

        with open(prompt_file, "r", encoding="utf-8") as pf:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=pf,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # 지침서를 통째로 싣는 자리(캐러셀 문구)는 프롬프트가 2만 자를 넘는다 —
            # 120초로는 모자라 codex 폴백이 그대로 시간 초과로 죽었다(2026-09-28).
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"gemini CLI error (exit {proc.returncode}): {err}")

        return stdout.decode("utf-8", errors="replace").strip()
    finally:
        try:
            os.unlink(prompt_file)
        except OSError:
            # ⚠ 윈도우에서는 CLI 가 아직 파일을 물고 있으면 지워지지 않는다(WinError 32).
            #   임시 파일 하나 남는 것보다, 답을 다 받아 놓고 **여기서 터지는 쪽**이 훨씬 나쁘다
            #   (2026-09-28 — 주제 생성이 답을 받고도 이 줄에서 죽었다).
            pass


async def _log_codex_usage(model: str, stdout: bytes) -> None:
    """`codex exec --json` 이 뱉은 이벤트에서 토큰 수를 건져 기록한다.

    캐시 적중을 눈으로 볼 수 있게 하려고 만든 것이다 — 캐싱은 자동으로 돌지만
    적중하는지 알 방법이 없으면 도는지 확인할 수가 없다.
    ``usage_logs`` 테이블에는 input/output 칸만 있어 캐시 수치는 로그로만 남긴다.
    """
    try:
        usage = None
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or "usage" not in line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and isinstance(event.get("usage"), dict):
                usage = event["usage"]  # 마지막 것이 그 턴의 최종 집계다
        if not usage:
            return

        total_in = int(usage.get("input_tokens") or 0)
        cached = int(usage.get("cached_input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
        hit = (cached / total_in * 100) if total_in else 0.0
        logger.info(
            f"[LLM/codex] {model} usage: input={total_in} (cached={cached}, {hit:.0f}%) output={out}"
        )
        await _log_usage(model, total_in, out, call_type="text")
    except Exception as e:
        logger.debug(f"[LLM/codex] usage 집계 실패: {e}")


async def _call_codex_cli(
    prompt: str,
    system: str | None = None,
    model: str = "gpt-6-sol",
    timeout: float = 180.0,
    json_schema: dict | None = None,
    images: list[str] | None = None,
) -> str:
    """Call Codex via `codex exec` (non-interactive).

    `images` — 모델에게 보여 줄 로컬 그림 경로(`-i`). 훅 창고가 표지 글자를 읽을 때 쓴다.

    플래그는 2026-09-02 에 codex-cli 0.147.0 으로 하나씩 확인한 것이다:
      exec                   비대화형. 빼면 대화 UI 가 떠서 서버가 그대로 멈춘다.
      -o <file>              **마지막 답만** 파일로 받는다. stdout 에는 진행 로그가 섞인다.
      -                      프롬프트를 stdin 으로 넣는다(긴 한글·따옴표가 인자에서 깨지지 않게).
      --sandbox read-only    문구만 짓게 한다. 모델이 셸을 잡지 못한다.
      --skip-git-repo-check  서버 작업 폴더가 git 저장소가 아닐 수 있다.
      --ephemeral            세션 파일을 디스크에 남기지 않는다(서버에 쌓이면 안 된다).
      --json                 stdout 에 이벤트를 JSONL 로. 마지막 turn.completed 에 토큰 수가 온다.
      --output-schema <파일>  답의 **모양을 강제**한다. 프롬프트로 "이 형식으로 줘" 라고만 하면
                             모델이 칸 이름을 한글로 바꾸거나 개수를 줄여서 낸다 — 실제로
                             주제 10개 대신 「추천 3개」가 `{주제, 왜}` 로 와서 화면이 비었다
                             (2026-09-02). 스키마를 걸면 그런 변형이 원천적으로 막힌다.

    로그인된 Codex 세션을 쓰므로 API 키가 필요 없다.

    프롬프트 캐싱은 **자동이다** — 붙일 표시(cache_control 같은 것)가 없고, 실측에서도
    아무 설정 없이 28,300 토큰 중 21,248 이 이미 캐시로 읽혔다(2026-09-02). 캐시되는 것은
    주로 codex 자신의 시스템 프롬프트다. 그래서 우리 프롬프트를 「고정 + 가변」 으로 쪼개도
    얻는 것이 없다 — 우리 몫은 631 토큰뿐이라 캐시 최소 단위(1,024)에도 못 미친다.
    """
    full_prompt = prompt
    if system:
        full_prompt = f"[System Instructions]\n{system}\n\n[User Request]\n{prompt}"

    workdir = tempfile.mkdtemp(prefix="codex_llm_")
    prompt_file = os.path.join(workdir, "prompt.txt")
    out_file = os.path.join(workdir, "answer.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(full_prompt)

    schema_file = None
    if json_schema:
        schema_file = os.path.join(workdir, "schema.json")
        with open(schema_file, "w", encoding="utf-8") as f:
            json.dump(json_schema, f, ensure_ascii=False)

    try:
        cmd = [
            CODEX_CLI, "exec",
            "-m", model,
            "-c", f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"',
            *_codex_lean_flags(),
            "--sandbox", "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--color", "never",
            "--json",
            "-o", out_file,
        ]
        if schema_file:
            cmd += ["--output-schema", schema_file]
        for image in images or []:
            cmd += ["-i", image]
        cmd.append("-")

        with open(prompt_file, "r", encoding="utf-8") as pf:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=pf,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            # `--json` 이면 실패 사유가 stderr 가 아니라 **stdout 이벤트**(error · turn.failed)로 온다.
            # stderr 만 보면 「exit 1: 」 처럼 빈 사유만 남아 원인을 못 찾았다(2026-10-05).
            events = []
            for line in stdout.decode("utf-8", errors="replace").splitlines():
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("type") in ("error", "turn.failed"):
                    msg = ev.get("message") or (ev.get("error") or {}).get("message") or ""
                    if msg:
                        events.append(str(msg))
            detail = " | ".join(events[-2:]) or err
            raise RuntimeError(f"codex CLI error (exit {proc.returncode}): {detail[-400:]}")

        if not os.path.exists(out_file):
            raise RuntimeError("codex CLI 가 답을 남기지 않았습니다 (-o 파일 없음)")

        # 토큰 수는 답이 아니라 이벤트 스트림으로만 온다. 여기서 못 건지면 비용을 볼 방법이 없다.
        # 집계 실패가 문구 생성을 막아서는 안 되므로 통째로 감싼다.
        await _log_codex_usage(model, stdout)

        with open(out_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ─── API Backend (fallback) ───

async def _call_api(
    model_id: str,
    messages: list[dict[str, str]],
    system: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    json_mode: bool = False,
) -> str:
    """Fallback: call LLM via LiteLLM API (requires API key)."""
    import litellm
    litellm.suppress_debug_info = True

    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    kwargs: dict[str, Any] = {
        "model": model_id,
        "messages": full_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = await litellm.acompletion(**kwargs)

    # Persist token usage so cost is auditable across restarts.
    try:
        usage = getattr(response, "usage", None)
        if usage:
            await _log_usage(
                model_id,
                getattr(usage, "prompt_tokens", 0) or 0,
                getattr(usage, "completion_tokens", 0) or 0,
                call_type="text",
            )
    except Exception:
        pass

    return response.choices[0].message.content


# ─── Core LLM Call (auto-routes CLI vs API) ───

async def llm_call(
    model: str,
    messages: list[dict[str, str]],
    system: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    json_mode: bool = False,
    json_schema: dict | None = None,
) -> str:
    """Make an LLM call — routes to CLI first, API as fallback.

    json_schema: codex 에서만 쓴다 — 답의 모양을 CLI 가 강제한다. 다른 provider 는 무시한다.

    Args:
        model: Short name (e.g. "opus", "gemini-flash") or full model ID
        messages: List of {"role": ..., "content": ...}
        system: Optional system prompt
        temperature: 0.0-1.0 (only used for API calls)
        max_tokens: Max output tokens
        json_mode: If True, request JSON output (adds instruction for CLI)

    Returns:
        The LLM's response text
    """
    entry = MODELS.get(model)
    if not entry:
        # Unknown model → direct API call
        logger.warning(f"[LLM] Unknown model '{model}', attempting API call")
        return await _call_api(model, messages, system, temperature, max_tokens, json_mode)

    provider = entry["provider"]

    # Build prompt text from messages
    prompt_parts = []
    for msg in messages:
        if msg["role"] == "user":
            prompt_parts.append(msg["content"])
        elif msg["role"] == "assistant":
            prompt_parts.append(f"[Assistant]: {msg['content']}")
    prompt_text = "\n\n".join(prompt_parts)

    if json_mode:
        prompt_text += "\n\n반드시 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력하세요."

    # Route: CLI first → API fallback
    if _can_use_cli(provider):
        try:
            if provider == "claude":
                result = await _call_claude_cli(
                    prompt_text, system=system,
                    model=entry["cli_model"], max_tokens=max_tokens,
                )
            elif provider == "codex":
                # 「Selected model is at capacity」 — OpenAI 쪽이 잠깐 붐빈 것이다(2026-10-05 실측:
                # 5개 동시 호출 중 1개). 바로 sonnet 폴백으로 넘기면 문구 결이 달라지고 돈이 든다.
                # 몇 초 뒤 다시 부르면 대개 된다 → 붐빔일 때만 두 번 더 기다렸다 부른다.
                for attempt, wait in enumerate((0, 4, 10)):
                    if wait:
                        logger.info(f"[LLM/CLI] {model} 붐빔 — {wait}초 뒤 다시 부릅니다({attempt}/2)")
                        await asyncio.sleep(wait)
                    try:
                        result = await _call_codex_cli(
                            prompt_text, system=system,
                            model=entry["cli_model"], json_schema=json_schema,
                        )
                        break
                    except RuntimeError as e:
                        if "at capacity" not in str(e) or attempt == 2:
                            raise
            else:  # gemini
                result = await _call_gemini_cli(
                    prompt_text, system=system,
                    model=entry["cli_model"],
                )
            logger.debug(f"[LLM/CLI] {model} → {len(result)} chars")
            return result
        except Exception as e:
            logger.warning(f"[LLM/CLI] {model} failed: {e}, trying API fallback...")
            if not _has_api_key(provider) and not entry.get("fallback"):
                raise  # API 키도 폴백 모델도 없다

    # API fallback
    if _has_api_key(provider):
        result = await _call_api(
            entry["model_id"], messages, system, temperature, max_tokens, json_mode
        )
        logger.debug(f"[LLM/API] {model} → {len(result)} chars")
        return result

    # 폴백 모델이 지정돼 있으면 마지막으로 그쪽에 맡긴다.
    # codex-sol 이 이 경우다 — prod 서버에는 codex CLI 가 없을 수 있는데, 그때 문구 생성이
    # 통째로 죽는 것보다 예전 모델(gemini-flash)로 짓는 편이 낫다.
    fallback = entry.get("fallback")
    if fallback and fallback != model:
        logger.warning(f"[LLM] '{model}' 을 쓸 수 없어 '{fallback}' 로 넘깁니다")
        return await llm_call(fallback, messages, system, temperature, max_tokens, json_mode, json_schema)

    raise RuntimeError(
        f"[LLM] No way to call '{model}': "
        f"CLI {'available' if _can_use_cli(provider) else 'not found'}, "
        f"API key {'set' if _has_api_key(provider) else 'not set'}. "
        f"Install the CLI tool or set the API key."
    )


# Fallback chain for Gemini Vision — preview models 503 a lot, so cascade to stable.
# Order: try requested model → fall through this list (skipping the one we just tried).
_VISION_FALLBACK_CHAIN = ["gemini-3.1-pro", "gemini-pro", "gemini-flash-thinking", "gemini-flash"]


async def gemini_vision(
    image_paths: list[str],
    prompt: str,
    system: str | None = None,
    model: str = "gemini-flash",
    json_mode: bool = True,
    max_tokens: int = 4096,
    image_labels: list[str] | None = None,
) -> dict | list | str:
    """Call Gemini with images + text prompt. Returns parsed JSON when json_mode=True.

    image_labels: optional per-image text inserted immediately BEFORE each image
    (same length as image_paths). Grounds each image to an explicit identity
    (e.g. "SLIDE index=6") so the model can't misassign text across images.

    Vision requires API access (CLI doesn't support image input) — needs GEMINI_API_KEY.

    Resilience: each model retries on 429/503 with exponential backoff. If the
    primary model stays unavailable, falls back through ``_VISION_FALLBACK_CHAIN``
    (e.g. gemini-3.1-pro → gemini-pro → gemini-flash) so preview-model outages
    don't break template creation entirely.
    """
    import base64
    import mimetypes

    entry = MODELS.get(model) or MODELS["gemini-flash"]
    model_id = entry["model_id"]
    provider = entry.get("provider", "gemini")

    if provider == "gemini" and not _has_api_key("gemini"):
        raise RuntimeError(
            "Gemini Vision requires GEMINI_API_KEY (or GOOGLE_API_KEY) — CLI does not support image input."
        )
    if provider == "claude" and not _has_api_key("claude"):
        raise RuntimeError(
            "Claude Vision requires ANTHROPIC_API_KEY."
        )

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for i, path in enumerate(image_paths):
        mime, _ = mimetypes.guess_type(path)
        if not mime:
            mime = "image/jpeg"
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        if image_labels and i < len(image_labels) and image_labels[i]:
            content.append({"type": "text", "text": image_labels[i]})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })

    messages = [{"role": "user", "content": content}]

    import litellm
    litellm.suppress_debug_info = True

    full_messages: list[dict[str, Any]] = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    # Build the fallback ladder — requested model first, then any others in the chain.
    tried: set[str] = set()
    ladder: list[str] = [model] + [m for m in _VISION_FALLBACK_CHAIN if m != model]
    last_err: Exception | None = None
    response = None

    for ladder_model in ladder:
        if ladder_model in tried:
            continue
        tried.add(ladder_model)
        cur_entry = MODELS.get(ladder_model)
        if not cur_entry:
            continue
        cur_model_id = cur_entry["model_id"]

        kwargs: dict[str, Any] = {
            "model": cur_model_id,
            "messages": full_messages,
            "temperature": 0.3,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        # Per-model retry on transient 429 / 503 with exponential backoff.
        max_retries = 4
        delay = 4.0
        gave_up = False
        for attempt in range(max_retries + 1):
            try:
                response = await litellm.acompletion(**kwargs)
                if ladder_model != model:
                    logger.warning(f"[Vision] succeeded on fallback model '{ladder_model}' (requested '{model}')")
                model_id = cur_model_id  # so the usage log below reflects the real model used
                break
            except Exception as e:
                last_err = e
                msg = str(e)
                is_rate = "429" in msg or "RateLimit" in msg or "Resource exhausted" in msg
                is_unavailable = (
                    "503" in msg
                    or "ServiceUnavailable" in msg
                    or "UNAVAILABLE" in msg
                    or "high demand" in msg
                )
                if not (is_rate or is_unavailable) or attempt == max_retries:
                    gave_up = True
                    break
                # Parse retry-after hint if present ("retry in 37s" / "retryDelay: 37")
                import re as _re
                m = _re.search(r"retry.{0,10}?(\d+)\s*s", msg, _re.IGNORECASE)
                wait = max(float(m.group(1)), delay) if m else delay
                wait = min(wait, 60.0)
                kind = "429" if is_rate else "503"
                logger.warning(
                    f"[Vision] {kind} on '{ladder_model}' attempt {attempt + 1}, waiting {wait:.1f}s"
                )
                await asyncio.sleep(wait)
                delay *= 2

        if response is not None:
            break
        # gave_up=True means this model exhausted its retries — try the next in the ladder.
        if gave_up:
            logger.warning(f"[Vision] '{ladder_model}' exhausted, falling back to next model")
            continue

    if response is None:
        raise last_err or RuntimeError("Vision retry exhausted across all fallback models")

    text = response.choices[0].message.content

    # Log token usage so callers can compute cost
    try:
        usage = getattr(response, "usage", None)
        if usage:
            it = getattr(usage, "prompt_tokens", 0) or 0
            ot = getattr(usage, "completion_tokens", 0) or 0
            logger.info(f"[Vision] {model_id} usage: input={it} output={ot}")
            _USAGE_TOTALS["input"] = _USAGE_TOTALS.get("input", 0) + it
            _USAGE_TOTALS["output"] = _USAGE_TOTALS.get("output", 0) + ot
            _USAGE_TOTALS["calls"] = _USAGE_TOTALS.get("calls", 0) + 1
            await _log_usage(model_id, it, ot, call_type="vision")
    except Exception:
        pass

    if not json_mode:
        return text

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if "```" in text:
            code = text.split("```")[1]
            if code.startswith("json"):
                code = code[4:]
            try:
                return json.loads(code.strip())
            except json.JSONDecodeError:
                pass
        logger.warning(f"[Vision] Failed to parse JSON from {model}, returning raw")
        return {"raw": text}


async def gemini_image_edit(
    image_paths: list[str],
    prompt: str,
    model: str = "nanobanana2",
    timeout: float = 120.0,
) -> bytes:
    """Image-to-image / image edit via Gemini (nanobanana / nanobanana2).

    Sends one or more reference images + a text prompt and returns the generated
    image bytes (PNG). Used for re-styling real photos to match a brand template.
    """
    if not _has_api_key("gemini"):
        raise RuntimeError("GEMINI_API_KEY 또는 GOOGLE_API_KEY 가 필요합니다 (이미지 생성)")

    entry = MODELS.get(model)
    if not entry:
        raise RuntimeError(f"알 수 없는 이미지 모델: {model}")
    model_id = entry["model_id"]

    # Use the google-genai SDK directly — LiteLLM doesn't yet wrap image-output.
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)

    parts: list[Any] = [types.Part.from_text(text=prompt)]
    for path in image_paths:
        with open(path, "rb") as f:
            data = f.read()
        mime = "image/jpeg"
        lower = path.lower()
        if lower.endswith(".png"):
            mime = "image/png"
        elif lower.endswith(".webp"):
            mime = "image/webp"
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))

    def _call_sync() -> bytes:
        response = client.models.generate_content(
            model=model_id,
            contents=parts,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
        # Find the inline image part in the response
        for cand in response.candidates or []:
            for p in (cand.content.parts if cand.content else []):
                inline = getattr(p, "inline_data", None)
                if inline and getattr(inline, "data", None):
                    return inline.data
        raise RuntimeError("Gemini 응답에서 이미지를 찾지 못했습니다")

    return await asyncio.wait_for(asyncio.to_thread(_call_sync), timeout=timeout)


async def llm_json(
    model: str,
    messages: list[dict[str, str]],
    system: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    json_schema: dict | None = None,
) -> dict | list:
    """Make an LLM call and parse the response as JSON.

    json_schema 를 주면 codex 가 그 모양을 **강제**한다 — 프롬프트로 부탁만 하면
    칸 이름·개수가 흔들린다(2026-09-02 실측).
    """
    text = await llm_call(
        model=model, messages=messages, system=system,
        temperature=temperature, max_tokens=max_tokens, json_mode=True,
        json_schema=json_schema,
    )

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` blocks
    if "```" in text:
        code = text.split("```")[1]
        if code.startswith("json"):
            code = code[4:]
        try:
            return json.loads(code.strip())
        except json.JSONDecodeError:
            pass

    logger.warning(f"[LLM] Failed to parse JSON from {model}, returning raw text")
    return {"raw": text}


# ─── Multi-Model Consensus ───

async def llm_consensus(
    models: list[str],
    messages: list[dict[str, str]],
    system: str | None = None,
    temperature: float = 0.5,
    max_tokens: int = 4096,
) -> list[dict[str, Any]]:
    """Call multiple models in parallel and return all responses."""
    tasks = [
        llm_call(model, messages, system, temperature, max_tokens)
        for model in models
    ]

    results_raw = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for model, result in zip(models, results_raw):
        if isinstance(result, Exception):
            results.append({
                "model": resolve_model(model),
                "response": None,
                "error": str(result),
            })
        else:
            results.append({
                "model": resolve_model(model),
                "response": result,
                "error": None,
            })

    return results


# ─── Convenience Wrappers ───

async def ask_claude(prompt: str, system: str | None = None, model: str = "sonnet") -> str:
    """Quick call to Claude (CLI or API)."""
    return await llm_call(model, [{"role": "user", "content": prompt}], system=system)


async def ask_gemini(prompt: str, system: str | None = None, model: str = "gemini-flash") -> str:
    """Quick call to Gemini (CLI or API)."""
    return await llm_call(model, [{"role": "user", "content": prompt}], system=system)


# Legacy aliases
ask_opus = lambda prompt, system=None: ask_claude(prompt, system, "opus")
ask_gemini_thinking = lambda prompt, system=None: ask_gemini(prompt, system, "gemini-flash-thinking")


# ─── Status Check ───

def get_llm_status() -> dict:
    """Return current LLM availability status."""
    status = {}
    for name, entry in MODELS.items():
        provider = entry["provider"]
        cli_ok = _can_use_cli(provider)
        api_ok = _has_api_key(provider)
        status[name] = {
            "provider": provider,
            "cli_available": cli_ok,
            "api_available": api_ok,
            "usable": cli_ok or api_ok,
            "mode": "cli" if cli_ok else ("api" if api_ok else "unavailable"),
        }
    return status
