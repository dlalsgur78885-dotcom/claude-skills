"""Unified LLM client — CLI-first, API-fallback.

Calls `claude` and `gemini` CLI tools directly when available,
falling back to LiteLLM API only when CLI is unavailable or an API key is set.

CLI tools used:
  claude -p "prompt" --output-format text   (Claude Code CLI)
  gemini -p "prompt"                        (Google Gemini CLI)

Environment variables (only needed if CLI unavailable):
  ANTHROPIC_API_KEY  - for Claude models via API
  GEMINI_API_KEY     - for Gemini models via API
"""

import asyncio
import json
import logging
import os
import shutil
import tempfile
from typing import Any

logger = logging.getLogger(__name__)

# ─── CLI Detection ───

CLAUDE_CLI = shutil.which("claude")
GEMINI_CLI = shutil.which("gemini")

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
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"claude CLI error (exit {proc.returncode}): {err}")

        return stdout.decode("utf-8", errors="replace").strip()
    finally:
        os.unlink(prompt_file)


async def _call_gemini_cli(
    prompt: str,
    system: str | None = None,
    model: str = "gemini-2.5-flash",
) -> str:
    """Call Gemini via `gemini` CLI."""
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
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"gemini CLI error (exit {proc.returncode}): {err}")

        return stdout.decode("utf-8", errors="replace").strip()
    finally:
        os.unlink(prompt_file)


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
) -> str:
    """Make an LLM call — routes to CLI first, API as fallback.

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
            else:  # gemini
                result = await _call_gemini_cli(
                    prompt_text, system=system,
                    model=entry["cli_model"],
                )
            logger.debug(f"[LLM/CLI] {model} → {len(result)} chars")
            return result
        except Exception as e:
            logger.warning(f"[LLM/CLI] {model} failed: {e}, trying API fallback...")
            if not _has_api_key(provider):
                raise  # No API key to fall back to

    # API fallback
    if _has_api_key(provider):
        result = await _call_api(
            entry["model_id"], messages, system, temperature, max_tokens, json_mode
        )
        logger.debug(f"[LLM/API] {model} → {len(result)} chars")
        return result

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
) -> dict | list:
    """Make an LLM call and parse the response as JSON."""
    text = await llm_call(
        model=model, messages=messages, system=system,
        temperature=temperature, max_tokens=max_tokens, json_mode=True,
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
